"""Process-isolated weekly pipeline orchestrator.

Each phase runs in its OWN `python app.py <cmd>` subprocess. This exists
because a single-process weekly run segfaulted: the CNPq/Lattes phases churn
native browser code (Playwright/Selenium), and heap corruption there crashed
a later native SQLite call in the Lattes ingest — taking the whole run (and
the export/anonymize steps) down with it.

Isolation gives each phase clean native + SQLite state, so one phase crashing
(segfault, timeout, exception) no longer aborts the others. The exports still
run and publish whatever the sources produced, while a failure in any
*critical* phase (sources missing, export, or LGPD anonymization) still makes
the overall run exit non-zero so CI and Telegram surface it — instead of the
old fail-open behavior that reported success on partial data.

Every phase is driven through `app.py`, never `python -m ...`, because the
LGPD `before_flush` anonymization hook is installed at app.py import time;
a phase that bypassed it would write raw PII to the database.
"""

import subprocess
import sys
import time
from typing import Optional

from loguru import logger

# (name, app.py argv tail, timeout seconds, critical)
# Order is load-bearing: SigPesq -> CNPq -> Lattes, then consolidation, exports, then LGPD.
_PHASES = [
    ("sigpesq", ["sigpesq"], 3600, True),
    ("cnpq", ["cnpq_sync"], 5400, False),
    ("lattes_download", ["lattes_download"], 5400, False),
    ("lattes_projects", ["ingest_lattes_projects"], 3600, False),
    ("lattes_advisorships", ["lattes_advisorships"], 1800, False),
    ("consolidate_duplicates", ["consolidate_duplicates"], 300, False),
    ("export_canonical", ["export_canonical"], 1800, True),
    ("knowledge_areas_mart", ["ka_mart"], 900, False),
    ("initiatives_analytics_mart", ["analytics_mart"], 900, False),
    ("people_relationship_graph", ["people_graph"], 1800, False),
    ("export_zip", [], 300, False),
    ("anonymize_backfill", ["anonymize_backfill"], 1800, True),
]


def _describe_rc(rc: Optional[int]) -> str:
    if rc is None:
        return "timeout"
    if rc < 0:
        return f"killed by signal {-rc}"
    if rc > 128:
        return f"killed by signal {rc - 128}"  # shell convention (139 = SIGSEGV)
    return f"exit {rc}"


def _run_phase(name, argv_tail, timeout, campus, output_dir):
    if name == "export_zip":
        argv = [sys.executable, "scripts/export_zip.py", "--clean-loose", output_dir]
    else:
        argv = [sys.executable, "app.py", *argv_tail]
        # Pass positional args only where app.py expects them.
        if argv_tail[0] == "cnpq_sync" and campus:
            argv.append(campus)
        elif argv_tail[0] == "export_canonical":
            argv.append(output_dir)
            if campus:
                argv.append(campus)
    logger.info("▶ phase '{}': {}", name, " ".join(argv[1:]))
    t0 = time.time()
    try:
        proc = subprocess.run(argv, timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        logger.error("phase '{}' timed out after {}s", name, timeout)
        rc = None
    elapsed = time.time() - t0
    ok = rc == 0
    log = logger.info if ok else logger.error
    log("phase '{}' finished: {}", name, _describe_rc(rc))
    from src.core.logic.provenance_tracker import ProvenanceTracker

    origin = ProvenanceTracker.get_provenance(name, output_dir)
    return {
        "name": name,
        "ok": ok,
        "rc": rc,
        "critical": bool(argv_tail and _critical(name)),
        "elapsed": elapsed,
        "origin": origin,
    }


def _critical(name):
    for n, _a, _t, crit in _PHASES:
        if n == name:
            return crit
    return False


def _notify(results, crit_failed, total_elapsed):
    from src.notifications.telegram import send_telegram_message

    head = "❌ Weekly ETL FALHOU" if crit_failed else "✅ Weekly ETL concluído"
    lines = [head, ""]
    for r in results:
        mark = "✓" if r["ok"] else "✗"
        origin_tag = f" [{r.get('origin', 'LIVE')}]"
        lines.append(
            f"{mark} {r['name']}{origin_tag} — {_describe_rc(r['rc'])} ({r['elapsed']:.0f}s)"
        )
    lines.append(f"\nTempo total: {total_elapsed:.0f}s")
    if crit_failed:
        lines.append("")
        lines.append(
            "Fases críticas que falharam: " + ", ".join(r["name"] for r in crit_failed)
        )
    send_telegram_message("\n".join(lines))


def run_weekly(
    campus_name: Optional[str] = None, output_dir: str = "data/exports"
) -> int:
    """Run every weekly phase in its own subprocess. Returns a process exit code."""
    from src.core.logic.export_cache_bootstrapper import ExportCacheBootstrapper

    logger.info("Initializing export cache bootstrap...")
    ExportCacheBootstrapper().bootstrap(target_dir=output_dir)

    campus = (campus_name or "").strip()
    results = []
    total_start = time.time()
    for name, argv_tail, timeout, _crit in _PHASES:
        results.append(_run_phase(name, argv_tail, timeout, campus, output_dir))
    total_elapsed = time.time() - total_start

    failed = [r for r in results if not r["ok"]]
    crit_failed = [r for r in failed if r["critical"]]

    width = 68
    print(f"\n{'=' * width}")
    print("  Weekly pipelines — Summary")
    print(f"{'=' * width}")
    for i, r in enumerate(results, 1):
        flag = "✓" if r["ok"] else "✗"
        origin_tag = f"[{r.get('origin', 'LIVE')}]"
        print(
            f"  Step {i:>2}  {flag}  {r['name']:.<32s} {origin_tag:<16s}"
            f" {r['elapsed']:>6.1f}s"
        )
    print(f"{'─' * width}")
    print(f"  Total{' ' * (width - 13)} {total_elapsed:>6.1f}s")
    if failed:
        print()
        for r in failed:
            print(f"  FAIL  {r['name']} ({r['elapsed']:.1f}s)")
    print()

    try:
        _notify(results, crit_failed, total_elapsed)
    except Exception as exc:  # notification must never change the run outcome
        logger.warning("Telegram summary failed: {}", exc)

    if crit_failed:
        logger.error(
            "Weekly pipeline FAILED — critical phases: {}",
            ", ".join(r["name"] for r in crit_failed),
        )
        return 1
    if failed:
        logger.warning(
            "Weekly pipeline completed with non-critical failures: {}",
            ", ".join(r["name"] for r in failed),
        )
    return 0


if __name__ == "__main__":
    _campus = sys.argv[1] if len(sys.argv) > 1 else None
    _out = sys.argv[2] if len(sys.argv) > 2 else "data/exports"
    sys.exit(run_weekly(campus_name=_campus, output_dir=_out))
