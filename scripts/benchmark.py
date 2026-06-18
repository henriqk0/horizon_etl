#!/usr/bin/env python3
"""Benchmark Horizon ETL pipelines.

Measures wall-clock time, CPU usage (% of a single core), and peak PSS
memory (Proportional Set Size — no double-counting of shared pages) across
multiple runs.  Optionally runs one sequential (single-thread / single-CPU)
run and computes speedup = sequential_time / parallel_time.

Usage:
    python scripts/benchmark.py                              # all, 3 runs each
    python scripts/benchmark.py -n 5                         # 5 runs each
    python scripts/benchmark.py --targets pipeline           # specific target
    python scripts/benchmark.py --sequential                 # + 1 sequential run
    python scripts/benchmark.py --clean-cache --db-reset     # fully isolated
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from statistics import mean, stdev


PIPELINES = OrderedDict([
    ("full-refresh",      "Full pipeline (all campuses, DB reset)"),
    ("weekly-flows",      "Weekly pipeline (sources + exports + graphs)"),
    ("pipeline",          "Pipeline (Campus=Serra, existing DB)"),
    ("ingest-sigpesq",    "SigPesq ingestion (groups + projects + advisorships)"),
    ("ingest-lattes-full","Lattes full ingestion (download + projects)"),
    ("sync-cnpq",         "CNPq research groups sync"),
    ("export-canonical",  "Canonical data export"),
])

# Core targets that exercise each unique pipeline without overlapping SigPesq
# dependency (full-refresh already covers SigPesq ingestion).
DEFAULT_TARGETS = ["full-refresh", "ingest-lattes-full", "sync-cnpq", "export-canonical"]

DEFAULT_RUNS = 3
SAVE_FILE = "data/reports/benchmark_results.json"

SEQUENTIAL_ENV = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "PYTHON_EXECUTOR_MAX_WORKERS": "1",
    "PREFECT_TASK_SCHEDULING_DEFAULT_MAX_CONCURRENCY": "1",
}

_TIME_LINE_RE = re.compile(r"^BENCH_T\s+([\d.]+)%")


def log(msg):
    print(msg, file=sys.stderr)


def db_reset():
    log("  Resetting database...")
    subprocess.run(
        ["make", "db-reset"],
        capture_output=True, text=True, timeout=300,
    )


def clean_cache():
    cache_dir = "cache"
    if os.path.isdir(cache_dir):
        log(f"  Cleaning {cache_dir}/...")
        for entry in os.listdir(cache_dir):
            path = os.path.join(cache_dir, entry)
            try:
                os.remove(path)
            except OSError:
                subprocess.run(["rm", "-rf", path], capture_output=True)
    lattes_json = "data/lattes_json"
    if os.path.isdir(lattes_json):
        log(f"  Cleaning {lattes_json}/...")
        subprocess.run(
            ["rm", "-rf", f"{lattes_json}/"],
            capture_output=True, timeout=60,
        )
        os.makedirs(lattes_json, exist_ok=True)


# ---------------------------------------------------------------------------
# Memory monitoring (peak PSS via /proc — no shared-page double-count)
# ---------------------------------------------------------------------------

def _walk_pids(root_pid):
    """Recursively collect all descendant PIDs of *root_pid*."""
    pids = {root_pid}
    try:
        for tid in os.listdir(f"/proc/{root_pid}/task/"):
            try:
                with open(f"/proc/{root_pid}/task/{tid}/children") as f:
                    for cpid in f.read().split():
                        cpid = int(cpid)
                        pids.add(cpid)
                        pids.update(_walk_pids(cpid))
            except (OSError, IOError):
                pass
    except (OSError, IOError):
        pass
    return pids


def _read_pss_kb(pid):
    """Return PSS in KB for *pid* (via smaps_rollup), or fall back to RSS.

    PSS (Proportional Set Size) divides shared pages across sharing
    processes, so summing PSS across the process tree gives the true
    unique physical memory footprint without double-counting.
    """
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except (OSError, IOError, IndexError, ValueError):
        pass
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
        return int(parts[23]) * 4
    except (OSError, IOError, IndexError, ValueError):
        return 0


class MemMonitor:
    """Periodically polls /proc to track peak PSS of a process tree."""

    def __init__(self, root_pid, interval=0.5):
        self.root_pid = root_pid
        self.interval = interval
        self._stop = False
        self._samples_mb = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self._stop = True
        self.thread.join(timeout=10)

    def peak_mb(self):
        return max(self._samples_mb) if self._samples_mb else 0.0

    def _run(self):
        while not self._stop:
            try:
                total_kb = 0
                for pid in _walk_pids(self.root_pid):
                    total_kb += _read_pss_kb(pid)
                self._samples_mb.append(total_kb / 1024.0)
            except Exception:
                pass
            time.sleep(self.interval)


# ---------------------------------------------------------------------------
# Run logic
# ---------------------------------------------------------------------------

def run_and_measure(target, sequential=False):
    """Run a make target and return (elapsed, cpu_percent, peak_mem_mb, rc).

    CPU percentage is obtained from the shell ``time`` keyword (zsh), which
    accurately counts CPU time across the entire waited-for process tree.
    Memory (PSS) is sampled via ``/proc/<pid>/smaps_rollup`` polling.
    """
    env = os.environ.copy()
    cmd_parts = ["make", target]
    if sequential:
        env.update(SEQUENTIAL_ENV)
        cmd_parts = ["taskset", "-c", "0"] + cmd_parts

    cmd_str = " ".join(cmd_parts)
    log(f"  Running: {cmd_str}")

    shell_cmd = f"TIMEFMT='BENCH_T %P'; time {cmd_str}"
    proc = subprocess.Popen(
        ["zsh", "-c", shell_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )

    mem_mon = MemMonitor(proc.pid)
    mem_mon.start()

    start = time.perf_counter()
    stdout, stderr = proc.communicate(timeout=36000)
    elapsed = time.perf_counter() - start

    mem_mon.stop()
    peak_mb = mem_mon.peak_mb()

    cpu_percent = 0.0
    for line in stderr.splitlines():
        m = _TIME_LINE_RE.match(line)
        if m:
            cpu_percent = float(m.group(1))
            break

    return elapsed, cpu_percent, peak_mb, proc.returncode


def run_parallel_benchmark(target, desc, num_runs, do_db_reset, do_clean_cache):
    log(f"\n{'=' * 60}")
    log(f"Benchmarking: {target}")
    log(f"  {desc}")
    log(f"  Parallel runs: {num_runs}")
    log(f"{'=' * 60}")

    times, cpus, mems = [], [], []
    failures = 0

    for i in range(num_runs):
        if do_clean_cache:
            clean_cache()
        if do_db_reset:
            db_reset()

        elapsed, cpu_pct, mem_mb, rc = run_and_measure(target)
        times.append(elapsed)
        cpus.append(cpu_pct)
        mems.append(mem_mb)

        if rc != 0:
            failures += 1
            status = "FAIL"
        else:
            status = "OK"

        log(f"  Run {i + 1:2d}/{num_runs}: {elapsed:>8.2f}s  "
            f"CPU: {cpu_pct:>5.1f}%  Mem: {mem_mb:>7.1f} MB  [{status}]")

    avg_t = mean(times)
    avg_c = mean(cpus)
    avg_m = mean(mems)
    sd = stdev(times) if len(times) > 1 else 0.0
    mn, mx = min(times), max(times)

    log(f"  {'─' * 55}")
    log(f"  Average: {avg_t:>8.2f}s  CPU: {avg_c:>5.1f}%  "
        f"Mem: {avg_m:>7.1f} MB")
    log(f"  Min: {mn:>8.2f}s  Max: {mx:>8.2f}s  "
        f"Std: {sd:.2f}s  Failures: {failures}")

    return {
        "target": target,
        "description": desc,
        "mode": "parallel",
        "runs": num_runs,
        "times": [round(t, 3) for t in times],
        "cpu_percentages": [round(c, 1) for c in cpus],
        "mem_mb": [round(m, 1) for m in mems],
        "avg_seconds": round(avg_t, 3),
        "min_seconds": round(mn, 3),
        "max_seconds": round(mx, 3),
        "std_seconds": round(sd, 3),
        "avg_cpu_percent": round(avg_c, 1),
        "avg_mem_mb": round(avg_m, 1),
        "failures": failures,
    }


def run_sequential_benchmark(target, desc, do_db_reset, do_clean_cache):
    log(f"\n{'─' * 55}")
    log("  Sequential run (1 thread / 1 CPU):")
    log(f"{'─' * 55}")

    if do_clean_cache:
        clean_cache()
    if do_db_reset:
        db_reset()

    elapsed, cpu_pct, mem_mb, rc = run_and_measure(target, sequential=True)
    status = "OK" if rc == 0 else "FAIL"

    log(f"  Time: {elapsed:>8.2f}s  "
        f"Mem: {mem_mb:>7.1f} MB  [{status}]")

    return {
        "target": target,
        "mode": "sequential",
        "seconds": round(elapsed, 3),
        "mem_mb": round(mem_mb, 1),
        "returncode": rc,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(all_results, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "timestamp": datetime.now().isoformat(),
        "results": all_results,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"\nResults saved to {filepath}")


def print_summary(parallel_results, sequential_results):
    has_seq = bool(sequential_results)
    ncols = 80 + (20 if has_seq else 0)
    print(f"\n{'=' * ncols}")
    print("BENCHMARK SUMMARY")
    print(f"{'=' * ncols}")
    print(f"CPU% = % of a single core  |  Mem (PSS)  |  Speedup = sequential_time / parallel_time")
    print(f"{'─' * ncols}")

    hdr = (f"{'Pipeline':<35} {'Avg (s)':<9} {'CPU%':<7} "
           f"{'Mem (MB)':<10} {'±Std':<7} {'Runs':<6}")
    if has_seq:
        hdr += f" {'Seq (s)':<9} {'Speedup':<9}"
    print(hdr)
    sep = f"{'─' * 35} {'─' * 9} {'─' * 7} {'─' * 10} {'─' * 7} {'─' * 6}"
    if has_seq:
        sep += f" {'─' * 9} {'─' * 9}"
    print(sep)

    for p in parallel_results:
        name = p["target"]
        speedup_str = ""
        if has_seq and name in sequential_results:
            s = sequential_results[name]
            ratio = s["seconds"] / p["avg_seconds"] if p["avg_seconds"] > 0 else 0
            speedup_str = f" {s['seconds']:<9.2f} {ratio:<9.2f}x"

        print(f"{name:<35} {p['avg_seconds']:<9.2f} {p['avg_cpu_percent']:<7.1f} "
              f"{p['avg_mem_mb']:<10.1f} {p['std_seconds']:<7.2f} "
              f"{p['runs']:<6}{speedup_str}")

    print(f"{'=' * ncols}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Horizon ETL pipelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-n", "--runs", type=int, default=DEFAULT_RUNS,
        help=f"Parallel runs per pipeline (default: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--targets", nargs="+", choices=list(PIPELINES) + ["all"],
        default=DEFAULT_TARGETS,
        help="Specific targets to benchmark (default: full-refresh, ingest-lattes-full, sync-cnpq, export-canonical). Use 'all' for all pipelines.",
    )
    parser.add_argument(
        "--db-reset", action="store_true",
        help="Reset database before each pipeline run",
    )
    parser.add_argument(
        "--clean-cache", action="store_true",
        help="Remove cache/ and data/lattes_json/ before each run",
    )
    parser.add_argument(
        "--sequential", action="store_true",
        help="Also run 1 sequential (1-thread) run per pipeline and compute speedup",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Do not save results to file",
    )
    parser.add_argument(
        "--save-file", default=SAVE_FILE,
        help=f"Output file for results (default: {SAVE_FILE})",
    )

    args = parser.parse_args()

    targets_list = list(PIPELINES) if "all" in args.targets else args.targets
    targets = [(t, PIPELINES[t]) for t in targets_list if t in PIPELINES]

    log("Benchmark configuration:")
    log(f"  Pipelines: {len(targets)}")
    log(f"  Parallel runs: {args.runs}")
    log(f"  Sequential run: {args.sequential}")
    log(f"  DB reset before each run: {args.db_reset}")
    log(f"  Clean cache before each run: {args.clean_cache}")
    log(f"  Saving results: {not args.no_save}")

    parallel_results = []
    sequential_results = {}

    for name, desc in targets:
        p = run_parallel_benchmark(name, desc, args.runs,
                                    args.db_reset, args.clean_cache)
        parallel_results.append(p)

        if args.sequential:
            s = run_sequential_benchmark(name, desc,
                                          args.db_reset, args.clean_cache)
            sequential_results[name] = s

    print_summary(parallel_results, sequential_results)

    all_results = {"parallel": parallel_results}
    if sequential_results:
        all_results["sequential"] = {k: v for k, v in sequential_results.items()}
        speedups = {}
        for p in parallel_results:
            n = p["target"]
            if n in sequential_results:
                s = sequential_results[n]
                speedups[n] = round(s["seconds"] / p["avg_seconds"], 3) if p["avg_seconds"] > 0 else 0
        all_results["speedup"] = speedups

    if not args.no_save:
        save_results(all_results, args.save_file)

    total_failures = sum(r["failures"] for r in parallel_results)
    if total_failures > 0:
        log(f"\nWARNING: {total_failures} parallel run(s) failed overall.")
        sys.exit(1)


if __name__ == "__main__":
    main()
