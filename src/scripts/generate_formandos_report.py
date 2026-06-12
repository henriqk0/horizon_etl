"""
Gera o relatório HTML 'Formandos × Pesquisa' para IFES Serra.

Fonte:
  - data/formandos/formados_2024_1.xlsx  (lista de formandos)
  - data/exports/advisorships_canonical.json
  - data/exports/research_groups_canonical.json
  - data/exports/researchers_canonical.json

Metodologia de matching:
  Formandos são cruzados com advisorships_canonical por nome (person_name).
  Apenas pessoas que aparecem como person_id em orientações são consideradas
  "registradas no SigPesq como alunos de pesquisa".

Uso:
  python -m src.scripts.generate_formandos_report
  python -m src.scripts.generate_formandos_report --semester 2024_2
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import re

import openpyxl

# ---------------------------------------------------------------------------
# String normalization
# ---------------------------------------------------------------------------

_LOWER_WORDS = frozenset({
    "de", "da", "do", "das", "dos", "e", "a", "o", "em", "com",
    "para", "por", "ou", "um", "uma", "no", "na", "nos", "nas",
})
# Acronyms: all ASCII uppercase/digits, max 6 chars (PIBIC, CAPES, IFES, IA…)
_ACRONYM_RE = re.compile(r"^[A-Z0-9]{2,6}$")
# Preserve as-is: explicitly known mixed-case terms
_PRESERVE = frozenset({"CNPq", "SigPesq", "LaTeX", "OpenCV", "OpenAI"})


def normalize_str(text: str) -> str:
    """
    Normalize a knowledge-area / label string to Title Case.

    Rules (priority order):
      1. Word in _PRESERVE whitelist → keep as-is.
      2. Word (lowered) is PT preposition/article and not first word → lowercase.
      3. Word is pure ASCII uppercase, 2-6 chars → treat as acronym, keep as-is.
      4. Otherwise → capitalize first char, lowercase rest.
    """
    if not text or not text.strip():
        return text
    words = text.strip().split()
    result = []
    for i, word in enumerate(words):
        core = word.strip(".,;:()")
        if core in _PRESERVE:
            result.append(word)
        elif core.lower() in _LOWER_WORDS and i != 0:
            result.append(core.lower())
        elif _ACRONYM_RE.match(core):
            result.append(word)
        else:
            result.append(word[0].upper() + word[1:].lower() if word else word)
    return " ".join(result)


def normalize_name(text: str) -> str:
    """
    Normalize a person name to Title Case (no acronym preservation).
    Handles ALL_CAPS and all-lower inputs.
    """
    if not text or not text.strip():
        return text
    words = text.strip().split()
    result = []
    for i, word in enumerate(words):
        core = word.strip(".,;:()")
        if core.lower() in _LOWER_WORDS and i != 0:
            result.append(core.lower())
        else:
            result.append(word[0].upper() + word[1:].lower() if word else word)
    return " ".join(result)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[2]  # horizon_etl/
DATA_FORMANDOS = BASE / "data" / "formandos"
DATA_EXPORTS = BASE / "data" / "exports"
OUT_DIR = DATA_EXPORTS / "formandos"

SEMESTER_FILE_MAP = {
    "2024_1": "formados_2024_1.xlsx",
    "2024_2": "formados_2024_2.xlsx",
    "2025_1": "formados_2025_1.xlsx",
    "2025_2": "formados_2025_2.xlsx",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _parse_matricula(mat: str) -> dict | None:
    """Extract entry year and semester from matricula like '20181BSI0056'."""
    if not mat or len(mat) < 5:
        return None
    try:
        year = int(str(mat)[:4])
        sem = int(str(mat)[4])
        if sem not in (1, 2):
            return None
        return {"year": year, "semester": sem}
    except (ValueError, IndexError):
        return None


def load_formandos(semester: str) -> list[dict]:
    path = DATA_FORMANDOS / SEMESTER_FILE_MAP[semester]
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    return [
        {"nome": r[1], "curso": r[3], "matricula": r[0], "entry": _parse_matricula(str(r[0]))}
        for r in ws.iter_rows(values_only=True, min_row=2)
        if r[1]
    ]


def load_json(name: str) -> Any:
    return json.loads((DATA_EXPORTS / name).read_text())


def load_lattes() -> dict[str, list[dict]]:
    """
    Load all IC and TCC records from Lattes JSON files.
    Returns {'ic': [...], 'tcc': [...]}, each item has keys:
      orientando, titulo, ano_inicio, ano_conclusao, supervisor, status
    """
    lattes_dir = BASE / "data" / "lattes_json"
    ic: list[dict] = []
    tcc: list[dict] = []
    for f in sorted(lattes_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        nome_sup = normalize_name(
            (data.get("informacoes_pessoais") or {}).get("nome", "") or f.stem
        )
        for status in ("em_andamento", "concluidas"):
            d = (data.get("orientacoes") or {}).get(status, {}) or {}
            for item in d.get("iniciacao_cientifica", []):
                ic.append({
                    "orientando": (item.get("orientando") or "").strip(),
                    "titulo": item.get("titulo", ""),
                    "ano_inicio": item.get("ano_inicio"),
                    "ano_conclusao": item.get("ano_conclusao"),
                    "supervisor": nome_sup,
                    "status": status,
                })
            for item in d.get("tcc", []):
                tcc.append({
                    "orientando": (item.get("orientando") or "").strip(),
                    "titulo": item.get("titulo", ""),
                    "ano_inicio": item.get("ano_inicio"),
                    "ano_conclusao": item.get("ano_conclusao"),
                    "supervisor": nome_sup,
                    "status": status,
                })
    return {"ic": ic, "tcc": tcc}


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def compute(formandos: list[dict], adv_projects: list[dict],
            rgs: list[dict], lattes: dict[str, list[dict]] | None = None,
            grad_semester: str = "") -> dict:
    names_map: dict[str, str] = {
        f["nome"].lower().strip(): f["curso"] for f in formandos
    }
    entry_map: dict[str, dict] = {
        f["nome"].lower().strip(): f["entry"]
        for f in formandos
        if f.get("entry")
    }
    total = len(formandos)

    # ---- student matching: only person_ids that appear as advisee ----
    name_to_pid: dict[str, int] = {}
    for proj in adv_projects:
        for adv in proj.get("advisorships", []):
            pname = (adv.get("person_name") or "").lower().strip()
            pid = adv.get("person_id")
            if pname in names_map and pid:
                name_to_pid[pname] = pid

    matched_pids: set[int] = set(name_to_pid.values())
    matched_names: set[str] = set(name_to_pid.keys())

    sem_registro = total - len(matched_pids)

    # ---- advisorship records for matched formandos ----
    person_projects: dict[int, set] = defaultdict(set)
    person_supervisors: dict[int, set] = defaultdict(set)
    person_fellowship_records: dict[int, list] = defaultdict(list)
    sponsor_persons: dict[str, set] = defaultdict(set)
    fellowship_persons: dict[str, set] = defaultdict(set)
    sup_unique: dict[str, set] = defaultdict(set)
    person_first_ic: dict[int, datetime] = {}  # earliest IC start per person

    pid_to_name: dict[int, str] = {v: k for k, v in name_to_pid.items()}

    for proj in adv_projects:
        for adv in proj.get("advisorships", []):
            pid = adv.get("person_id")
            if pid not in matched_pids:
                continue
            person_projects[pid].add(proj["id"])
            sname = normalize_name(adv.get("supervisor_name") or "")
            if sname:
                person_supervisors[pid].add(sname)
                sup_unique[sname].add(pid)

            # track earliest IC start
            try:
                ic_start = datetime.fromisoformat((adv.get("start_date") or "")[:10])
                if pid not in person_first_ic or ic_start < person_first_ic[pid]:
                    person_first_ic[pid] = ic_start
            except Exception:
                pass

            fel = adv.get("fellowship") or {}
            if fel and fel.get("name"):
                sponsor = normalize_str(fel.get("sponsor_name") or "Voluntário")
                fname = normalize_str(fel["name"])
                year = (adv.get("start_date") or "")[:4]
                days: int | None = None
                try:
                    s = datetime.fromisoformat((adv["start_date"] or "")[:10])
                    e = datetime.fromisoformat((adv["end_date"] or "")[:10])
                    days = (e - s).days
                except Exception:
                    pass
                person_fellowship_records[pid].append({
                    "year": year,
                    "sponsor": sponsor,
                    "fellowship": fname,
                    "days": days,
                    "value": fel.get("value") or 0.0,
                })
                sponsor_persons[sponsor].add(pid)
                fellowship_persons[fname].add(pid)

    # ---- research groups ----
    rg_names: set[str] = set()
    rg_top: Counter = Counter()
    for rg in rgs:
        members_in = [
            m for m in (rg.get("members") or [])
            if (m.get("name") or "").lower().strip() in names_map
        ]
        if members_in:
            rg_top[normalize_str(rg.get("name", ""))] += len(members_in)
            for m in members_in:
                rg_names.add((m.get("name") or "").lower().strip())

    # add RG-only formandos to with_research
    rg_only_pids: set[int] = set()
    for n in rg_names - matched_names:
        # not already found via advisorships; we can't get pid easily
        pass

    with_research = len(matched_pids)  # all matched via advisorship have research
    sem_pesquisa = sem_registro  # unmatched ones have no research signal

    # ---- fellowship counts ----
    fellowship_counts = {k: len(v) for k, v in fellowship_persons.items()}
    sponsor_counts = {k: len(v) for k, v in sponsor_persons.items()}

    # ---- investment per sponsor ----
    sponsor_investment: dict[str, float] = defaultdict(float)
    for recs in person_fellowship_records.values():
        for r in recs:
            sponsor_investment[r["sponsor"]] += r["value"]

    # ---- sponsor × fellowship (unique persons) ----
    sponsor_fellowship_unique: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sf_persons: dict[tuple, set] = defaultdict(set)
    for pid, recs in person_fellowship_records.items():
        for r in recs:
            sf_persons[(r["sponsor"], r["fellowship"])].add(pid)
    for (s, f), pids in sf_persons.items():
        sponsor_fellowship_unique[s][f] = len(pids)

    # ---- curso × sponsor ----
    curso_sponsor: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    curso_sponsor_sets: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for pid, recs in person_fellowship_records.items():
        # find curso by name
        pid_name = next(
            (n for n, p in name_to_pid.items() if p == pid), None
        )
        if pid_name is None:
            continue
        curso = names_map.get(pid_name, "N/A")
        for r in recs:
            curso_sponsor_sets[curso][r["sponsor"]].add(pid)
    for curso, sps in curso_sponsor_sets.items():
        for s, pids in sps.items():
            curso_sponsor[curso][s] = len(pids)

    # ---- project distribution ----
    proj_dist = Counter(len(v) for v in person_projects.values())
    with_projects = len(person_projects)

    # ---- duration ----
    durations = [
        r["days"]
        for recs in person_fellowship_records.values()
        for r in recs
        if r["days"] and 30 < r["days"] < 800
    ]
    dur_mean = round(sum(durations) / len(durations)) if durations else 0
    dur_median = sorted(durations)[len(durations) // 2] if durations else 0
    dur_bins = Counter()
    for d in durations:
        if d <= 180:
            dur_bins["≤6m"] += 1
        elif d <= 365:
            dur_bins["7-12m"] += 1
        else:
            dur_bins[">12m"] += 1

    # ---- progressão ----
    prog: Counter = Counter()
    for pid, recs in person_fellowship_records.items():
        if len(recs) <= 1:
            continue
        sorted_recs = sorted(recs, key=lambda x: x["year"])
        sponsors = [r["sponsor"] for r in sorted_recs]
        paid = [s for s in sponsors if s != "Voluntário"]
        vol = [s for s in sponsors if s == "Voluntário"]
        if vol and paid:
            if sponsors[0] == "Voluntário":
                prog["vol→pago"] += 1
            elif sponsors[-1] == "Voluntário":
                prog["pago→vol"] += 1
            else:
                prog["misto"] += 1
        elif len(set(paid)) > 1:
            prog["multi-agencia"] += 1
    multi_bolsa = sum(
        1 for recs in person_fellowship_records.values() if len(recs) > 1
    )

    # ---- orientadores distribution ----
    sup_dist = Counter(len(v) for v in person_supervisors.values())
    top_sups = sorted(sup_unique.items(), key=lambda x: -len(x[1]))[:10]

    # ---- curso breakdown (with/without research) ----
    curso_with = Counter()
    curso_total = Counter(f["curso"] for f in formandos)
    for n in matched_names:
        curso_with[names_map[n]] += 1

    # ---- RG top ----
    rg_top_list = rg_top.most_common(8)

    # ---- KA from RGs (deduplicated by normalized key) ----
    _KA_TRANSLATE: dict[str, str] = {
        "machine learning": "Aprendizado de Máquina",
        "deep learning": "Aprendizado Profundo",
        "computer vision": "Visão Computacional",
        "natural language processing": "Processamento de Linguagem Natural",
        "internet of things": "Internet das Coisas",
        "iot": "Internet das Coisas",
        "data science": "Ciência de Dados",
        "big data": "Grandes Volumes de Dados",
        "embedded systems": "Sistemas Embarcados",
        "control systems": "Sistemas de Controle",
        "automation": "Automação",
        "robotics": "Robótica",
        "software engineering": "Engenharia de Software",
    }
    _ka_raw: dict[str, int] = defaultdict(int)
    for rg in rgs:
        members_in = [
            m for m in (rg.get("members") or [])
            if (m.get("name") or "").lower().strip() in names_map
        ]
        if not members_in:
            continue
        for ka in (rg.get("knowledge_areas") or []):
            raw_name = ka.get("name", "")
            translated = _KA_TRANSLATE.get(raw_name.lower().strip(), raw_name)
            key = normalize_str(translated)
            _ka_raw[key] += len(members_in)
    # merge near-duplicates: same normalized lower key
    _ka_merged: dict[str, int] = defaultdict(int)
    for k, v in _ka_raw.items():
        _ka_merged[k.lower()] = max(_ka_merged[k.lower()], v)
    # rebuild with proper casing (normalize again)
    ka_counter: Counter = Counter()
    for k, v in _ka_merged.items():
        ka_counter[normalize_str(k)] += v

    # ---- IC timing: when did students start IC relative to enrollment ----
    def _date_to_sem(year: int, month: int) -> tuple[int, int]:
        """Convert year/month to (year, semester): Jan-Jun → 1, Jul-Dec → 2."""
        return year, (1 if month <= 6 else 2)

    def _sem_diff(ey: int, es: int, iy: int, i_s: int) -> int:
        """Semesters from entry (ey/es) to IC start (iy/i_s)."""
        return (iy - ey) * 2 + (i_s - es)

    ic_period_dist: Counter = Counter()   # semesters after entry → count
    ic_year_dist: Counter = Counter()     # calendar year of first IC → count
    ic_timing_records: list[dict] = []    # per-person detail

    for pid, ic_date in person_first_ic.items():
        name = pid_to_name.get(pid, "")
        entry = entry_map.get(name)
        ic_year_dist[ic_date.year] += 1
        if entry:
            diff = _sem_diff(entry["year"], entry["semester"],
                             *_date_to_sem(ic_date.year, ic_date.month))
            if 0 <= diff <= 12:  # sanity: within 6 years
                ic_period_dist[diff] += 1
                ic_timing_records.append({
                    "name": normalize_name(name),
                    "entry": f"{entry['year']}/{entry['semester']}",
                    "ic_start": ic_date.strftime("%Y/%m"),
                    "semesters_after": diff,
                    "curso": names_map.get(name, ""),
                })

    ic_timing_records.sort(key=lambda x: x["semesters_after"])

    # average semesters to first IC (for those with entry data)
    timing_vals = [r["semesters_after"] for r in ic_timing_records]
    avg_timing = round(sum(timing_vals) / len(timing_vals), 1) if timing_vals else None

    ic_timing: dict = {
        "period_dist": dict(sorted(ic_period_dist.items())),
        "year_dist": dict(sorted(ic_year_dist.items())),
        "avg_semesters": avg_timing,
        "n_with_entry": len(ic_timing_records),
        "records": ic_timing_records,
    }

    # ---- graduation time (semesters from entry to graduation) ----
    _grad_overall: list[int] = []
    _grad_by_curso: dict[str, list[int]] = defaultdict(list)
    _grad_ic: list[int] = []
    _grad_no_ic: list[int] = []
    _grad_ic_by_curso: dict[str, list[int]] = defaultdict(list)
    _grad_no_ic_by_curso: dict[str, list[int]] = defaultdict(list)

    if grad_semester:
        try:
            _gy, _gs = int(grad_semester[:4]), int(grad_semester[5])
        except (ValueError, IndexError):
            _gy, _gs = 0, 0

        if _gy:
            for f in formandos:
                entry = f.get("entry")
                if not entry:
                    continue
                diff = _sem_diff(entry["year"], entry["semester"], _gy, _gs)
                if 1 <= diff <= 50:  # sanity: at least 1 sem, at most 25 years
                    _grad_overall.append(diff)
                    _grad_by_curso[f["curso"]].append(diff)
                    _nk = f["nome"].lower().strip()
                    if _nk in matched_names:
                        _grad_ic.append(diff)
                        _grad_ic_by_curso[f["curso"]].append(diff)
                    else:
                        _grad_no_ic.append(diff)
                        _grad_no_ic_by_curso[f["curso"]].append(diff)

    def _gstats(vals: list[int]) -> dict:
        if not vals:
            return {}
        sv = sorted(vals)
        n = len(sv)
        return {
            "n": n,
            "mean": round(sum(sv) / n, 1),
            "median": sv[n // 2],
            "min": sv[0],
            "max": sv[-1],
            "dist": dict(Counter(sv)),
        }

    def _gcategories(vals: list[int]) -> dict:
        transfers = [v for v in vals if v < 4]
        regular   = [v for v in vals if 4 <= v <= 24]
        extended  = [v for v in vals if v > 24]
        return {"transfers": len(transfers), "regular": len(regular), "extended": len(extended)}

    _all_cursos = sorted(set(list(_grad_by_curso.keys())))
    graduation_time = {
        "overall": _gstats(_grad_overall),
        "by_curso": {c: _gstats(v) for c, v in _grad_by_curso.items()},
        "categories": _gcategories(_grad_overall),
        "by_curso_categories": {c: _gcategories(v) for c, v in _grad_by_curso.items()},
        "ic_vs_no_ic": {
            "ic": _gstats(_grad_ic),
            "no_ic": _gstats(_grad_no_ic),
            "by_curso": {
                c: {
                    "ic": _gstats(_grad_ic_by_curso.get(c, [])),
                    "no_ic": _gstats(_grad_no_ic_by_curso.get(c, [])),
                }
                for c in _all_cursos
            },
        },
    }

    # ---- Lattes cross-reference ----
    lattes_cross: dict = {}
    if lattes:
        ic_recs = lattes.get("ic", [])
        tcc_recs = lattes.get("tcc", [])

        lattes_ic_names: set[str] = {
            r["orientando"].lower().strip()
            for r in ic_recs
            if r["orientando"].lower().strip() in names_map
        }
        lattes_tcc_names: set[str] = {
            r["orientando"].lower().strip()
            for r in tcc_recs
            if r["orientando"].lower().strip() in names_map
        }
        lattes_any_names = lattes_ic_names | lattes_tcc_names

        # Per-person project counts from Lattes
        lattes_ic_count: dict[str, int] = defaultdict(int)
        for r in ic_recs:
            n = r["orientando"].lower().strip()
            if n in names_map:
                lattes_ic_count[n] += 1

        lattes_tcc_count: dict[str, int] = defaultdict(int)
        for r in tcc_recs:
            n = r["orientando"].lower().strip()
            if n in names_map:
                lattes_tcc_count[n] += 1

        # SigPesq per-person project count (already have person_projects)
        sigpesq_name_count: dict[str, int] = {}
        for n, pid in name_to_pid.items():
            sigpesq_name_count[n] = len(person_projects.get(pid, set()))

        # Union coverage
        union_names = matched_names | lattes_any_names
        new_via_lattes = sorted(lattes_any_names - matched_names)

        # Combined project count per person (IC deduplicated, TCC additive)
        combined_count: dict[str, int] = {}
        for n in union_names:
            sp = sigpesq_name_count.get(n, 0)
            lt = lattes_ic_count.get(n, 0)
            tcc = lattes_tcc_count.get(n, 0)
            # IC: take max (same project may appear in both sources)
            # TCC: additive (SigPesq doesn't track TCC)
            combined_count[n] = max(sp, lt) + tcc

        def _avg(vals: list) -> float:
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        sp_vals = list(sigpesq_name_count.values())
        union_vals = list(combined_count.values())

        # Enriched: formandos where Lattes added TCC
        enriched = [
            {
                "name": normalize_name(n),
                "sigpesq": sigpesq_name_count.get(n, 0),
                "lattes_ic": lattes_ic_count.get(n, 0),
                "tcc": lattes_tcc_count.get(n, 0),
                "combined": combined_count[n],
            }
            for n in matched_names
            if combined_count.get(n, 0) > sigpesq_name_count.get(n, 0)
        ]
        enriched.sort(key=lambda x: -x["combined"])

        # Distribution: SigPesq vs Union
        sp_dist = dict(Counter(sp_vals))
        union_dist = dict(Counter(union_vals))

        lattes_cross = {
            "total_ic_lattes": len(ic_recs),
            "total_tcc_lattes": len(tcc_recs),
            "lattes_ic_formandos": len(lattes_ic_names),
            "lattes_tcc_formandos": len(lattes_tcc_names),
            "new_via_lattes": [normalize_name(n) for n in new_via_lattes],
            "sigpesq_n": len(matched_names),
            "union_n": len(union_names),
            "coverage_sigpesq_pct": round(len(matched_names) / total * 100, 1),
            "coverage_union_pct": round(len(union_names) / total * 100, 1),
            "avg_sigpesq": _avg(sp_vals),
            "avg_union": _avg(union_vals),
            "delta_avg": round(_avg(union_vals) - _avg(sp_vals), 2),
            "delta_pct": round((_avg(union_vals) / _avg(sp_vals) - 1) * 100, 1) if sp_vals else 0,
            "enriched_count": len(enriched),
            "enriched_top": enriched[:10],
            "sp_dist": sp_dist,
            "union_dist": union_dist,
        }

    return {
        "total": total,
        "sem_registro": sem_registro,
        "with_research": with_research,
        "sem_pesquisa": sem_pesquisa,
        "pct_research": round(with_research / total * 100, 1),
        "fellowship_counts": fellowship_counts,
        "sponsor_counts": sponsor_counts,
        "sponsor_investment": dict(sponsor_investment),
        "sponsor_fellowship_unique": {k: dict(v) for k, v in sponsor_fellowship_unique.items()},
        "curso_total": dict(curso_total),
        "curso_with": dict(curso_with),
        "curso_sponsor": {k: dict(v) for k, v in curso_sponsor.items()},
        "proj_dist": dict(proj_dist),
        "with_projects": with_projects,
        "durations_n": len(durations),
        "dur_mean": dur_mean,
        "dur_median": dur_median,
        "dur_bins": dict(dur_bins),
        "prog": dict(prog),
        "multi_bolsa": multi_bolsa,
        "sup_dist": dict(sup_dist),
        "top_sups": [(s, len(pids)) for s, pids in top_sups],
        "rg_top": rg_top_list,
        "ka_top": ka_counter.most_common(15),
        "total_with_fellowship": len(set().union(*fellowship_persons.values())) if fellowship_persons else 0,
        "lattes_cross": lattes_cross,
        "ic_timing": ic_timing,
        "graduation_time": graduation_time,
    }


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

CSS = """
:root {
  --bg:      #0a0f0a;
  --surface: #111811;
  --card:    #141f14;
  --border:  #1e2e1e;
  --green:   #00e676;
  --green2:  #69f0ae;
  --amber:   #ffd740;
  --blue:    #64b5f6;
  --red:     #ff5252;
  --gray:    #78909c;
  --text:    #e0f2e0;
  --sub:     #8fa88f;
  --font:    'Segoe UI', system-ui, sans-serif;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
@media print {
  :root { --bg:#fff; --surface:#fff; --card:#f8f8f8; --border:#ccc;
          --green:#1a7a3a; --green2:#2a8a4a; --amber:#7a5a00; --blue:#0a4a8a;
          --red:#8a1a1a; --text:#111; --sub:#444; }
  body { background:#fff !important; }
  .stat-card::before { display:none; }
}
body { background:var(--bg); color:var(--text); font-family:var(--font);
       min-height:100vh; padding:40px 24px 60px; }
header { text-align:center; margin-bottom:48px; }
header .eyebrow { font-size:11px; letter-spacing:3px; text-transform:uppercase;
                  color:var(--green); margin-bottom:10px; }
header h1 { font-size:clamp(22px,4vw,34px); font-weight:700; color:var(--text);
            margin-bottom:12px; }
header p { color:var(--sub); font-size:14px; }
.stats-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:28px; }
.stat-card { position:relative; background:var(--card); border:1px solid var(--border);
             border-radius:10px; padding:22px 20px; overflow:hidden; }
.stat-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--green); }
.stat-card .number { font-size:36px; font-weight:700; color:var(--green); line-height:1; }
.stat-card .pct { font-size:13px; color:var(--sub); margin-top:2px; }
.stat-card .label { font-size:12px; color:var(--sub); margin-top:8px; }
.section { background:var(--card); border:1px solid var(--border); border-radius:10px;
           padding:24px; margin-bottom:24px; }
.section h2 { font-size:15px; font-weight:600; color:var(--text); margin-bottom:16px; }
.section .sub { font-size:12px; color:var(--sub); margin-bottom:16px; }
.bar-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
.bar-row .lbl { font-size:11px; color:var(--text); width:180px; flex-shrink:0; }
.bar-row .lbl.sm { width:80px; }
.bar-row .lbl.md { width:120px; }
.bar-track { flex:1; height:12px; background:var(--border); border-radius:3px; overflow:hidden; }
.bar-track.sm { height:10px; }
.bar-fill { height:100%; }
.bar-row .val { font-size:11px; width:24px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.grid4 { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.mini-card { background:#0d1a0d; border:1px solid var(--border); border-radius:8px; padding:16px; }
.mini-card .agency { font-size:11px; letter-spacing:2px; text-transform:uppercase; margin-bottom:8px; }
.mini-card .big { font-size:28px; font-weight:700; color:var(--green); line-height:1; }
.mini-card .tiny { font-size:11px; color:var(--sub); }
.mini-card .divider { border-top:1px solid var(--border); margin:10px 0; padding-top:8px; }
.pill-row { display:flex; justify-content:space-between; font-size:11px; margin-bottom:3px; }
.prog-card { background:#0d1a0d; border:1px solid var(--border); border-radius:6px;
             padding:12px; text-align:center; }
.prog-card .pt { font-size:10px; color:var(--sub); text-transform:uppercase;
                 letter-spacing:1px; margin-bottom:6px; }
.prog-card .pn { font-size:24px; font-weight:700; }
.prog-card .ps { font-size:10px; color:var(--sub); margin-top:4px; }
.note { font-size:11px; color:var(--sub); line-height:1.6; padding:10px 12px;
        background:#0d1a0d; border-left:3px solid var(--sub); border-radius:4px; margin-top:12px; }
.note strong { color:var(--text); }
.list-row { display:flex; justify-content:space-between; font-size:11px;
            padding:4px 8px; background:#0d1a0d; border-radius:3px; margin-bottom:4px; }
footer { text-align:center; margin-top:48px; font-size:11px; color:var(--sub); }
"""


def bar(label: str, value: int, max_val: int, color: str,
        lbl_class: str = "") -> str:
    pct = value / max_val * 100 if max_val else 0
    return (
        f'<div class="bar-row">'
        f'<span class="lbl {lbl_class}">{label}</span>'
        f'<div class="bar-track"><div class="bar-fill" '
        f'style="width:{pct:.1f}%;background:{color};"></div></div>'
        f'<span class="val" style="color:{color};">{value}</span>'
        f'</div>'
    )


def mini_card_agency(name: str, color: str, count: int,
                     fellowship_breakdown: dict, investment: float) -> str:
    rows = "".join(
        f'<div class="pill-row"><span style="color:var(--text);">{k}</span>'
        f'<span style="color:var(--green);">{v}</span></div>'
        for k, v in sorted(fellowship_breakdown.items())
    )
    inv_str = (
        f'R$ {investment:,.0f}'.replace(",", ".")
        if investment > 0 else "R$ 0"
    )
    return f"""
    <div class="mini-card">
      <div class="agency" style="color:{color};">{name}</div>
      <div class="big">{count}</div>
      <div class="tiny">formandos</div>
      <div class="divider">
        <div style="font-size:10px;color:var(--sub);margin-bottom:6px;">Bolsas concedidas</div>
        {rows}
        <div style="margin-top:8px;">
          <div style="font-size:10px;color:var(--sub);">Investimento acumulado</div>
          <div style="font-size:13px;color:{color};font-weight:600;">
            {inv_str}<span style="font-size:10px;color:var(--sub);">/mês·bolsa</span>
          </div>
        </div>
      </div>
    </div>"""


def section(title: str, sub: str, body: str, border_color: str = "") -> str:
    style = f' style="border-color:{border_color};"' if border_color else ""
    return (
        f'<div class="section"{style}>'
        f'<h2>{title}</h2>'
        f'<div class="sub">{sub}</div>'
        f'{body}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------

def _sec_stats(s: dict) -> str:
    pct_sem = round(s["sem_pesquisa"] / s["total"] * 100, 1)
    return f"""
  <div class="stats-grid">
    <div class="stat-card">
      <div class="number">{s['total']}</div>
      <div class="label">formandos únicos</div>
    </div>
    <div class="stat-card">
      <div class="number">{s['with_research']}</div>
      <div class="pct">{s['pct_research']}% do total</div>
      <div class="label">com participação em pesquisa</div>
    </div>
    <div class="stat-card">
      <div class="number">{s['sem_pesquisa']}</div>
      <div class="pct">{pct_sem}% do total</div>
      <div class="label">sem participação em pesquisa</div>
    </div>
    <div class="stat-card">
      <div class="number">{s['sem_registro']}</div>
      <div class="label">sem registro no SigPesq</div>
    </div>
  </div>"""


def _sec_curso(s: dict) -> str:
    rows = ""
    for curso, total_c in sorted(s["curso_total"].items()):
        with_c = s["curso_with"].get(curso, 0)
        pct = round(with_c / total_c * 100, 1) if total_c else 0
        short = "ECA" if "Controle" in curso else "SI"
        rows += (
            f'<div style="margin-bottom:16px;">'
            f'<div style="font-size:12px;font-weight:600;margin-bottom:8px;">'
            f'{curso} <span style="color:var(--sub);">({total_c})</span></div>'
            f'{bar(f"com pesquisa", with_c, total_c, "var(--green)", "md")}'
            f'{bar(f"sem pesquisa", total_c-with_c, total_c, "var(--red)", "md")}'
            f'<div style="font-size:11px;color:var(--sub);margin-top:4px;">'
            f'{pct}% do {short} com pesquisa</div>'
            f'</div>'
        )
    return section("Distribuição por curso", "formandos por curso e participação", rows)


def _sec_fellowship(s: dict) -> str:
    counts = s["fellowship_counts"]
    if not counts:
        return ""
    max_v = max(counts.values())
    COLORS = {
        "PIBIC": "var(--green)", "PIVIC": "var(--green2)",
        "PIBITI": "var(--amber)", "PIVITI": "var(--blue)",
        "PIBIC-JR": "var(--gray)", "PROPÓS": "var(--gray)",
    }
    rows = "".join(
        bar(k, v, max_v, COLORS.get(k, "var(--sub)"))
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    )
    return section(
        "Tipo de bolsa",
        f"{s['total_with_fellowship']} formandos com pelo menos uma bolsa registrada",
        rows,
    )


def _sec_agencies(s: dict) -> str:
    AGENCY_COLORS = {
        "Fapes": "var(--amber)", "CNPq": "var(--blue)",
        "Ifes": "var(--green2)", "Voluntário": "var(--sub)",
    }
    order = ["Fapes", "CNPq", "Ifes", "Voluntário"]
    cards = "".join(
        mini_card_agency(
            ag,
            AGENCY_COLORS.get(ag, "var(--gray)"),
            s["sponsor_counts"].get(ag, 0),
            s["sponsor_fellowship_unique"].get(ag, {}),
            s["sponsor_investment"].get(ag, 0),
        )
        for ag in order
        if ag in s["sponsor_counts"]
    )

    paid = {k: v for k, v in s["sponsor_counts"].items() if k != "Voluntário"}
    max_paid = max(paid.values()) if paid else 1
    total_paid = sum(paid.values())
    bars_paid = "".join(
        bar(k, v, max_paid, AGENCY_COLORS.get(k, "var(--gray)"), "md")
        + f'<span style="font-size:10px;color:var(--sub);"> {round(v/total_paid*100)}%</span>'
        if total_paid else bar(k, v, max_paid, AGENCY_COLORS.get(k, "var(--gray)"), "md")
        for k, v in sorted(paid.items(), key=lambda x: -x[1])
    )

    # ---- investment indicators ----
    invest = {k: v for k, v in s["sponsor_investment"].items() if v > 0}
    total_invest = sum(invest.values())
    max_invest = max(invest.values()) if invest else 1

    def _fmt_brl(v: float) -> str:
        return f'R$ {v:,.0f}'.replace(",", "X").replace(".", ",").replace("X", ".")

    invest_bars = "".join(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
        f'<span style="font-size:12px;color:var(--text);width:90px;flex-shrink:0;">{ag}</span>'
        f'<div style="flex:1;height:14px;background:#1a2a1a;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{round(v/max_invest*100)}%;height:100%;background:{AGENCY_COLORS.get(ag,"var(--sub)")};">'
        f'</div></div>'
        f'<span style="font-size:12px;font-weight:600;color:{AGENCY_COLORS.get(ag,"var(--sub)")};width:90px;text-align:right;">'
        f'{_fmt_brl(v)}</span>'
        f'<span style="font-size:11px;color:var(--sub);width:80px;text-align:right;">'
        f'{_fmt_brl(v / s["sponsor_counts"].get(ag, 1))}/aluno</span>'
        f'</div>'
        for ag, v in sorted(invest.items(), key=lambda x: -x[1])
    )

    invest_block = (
        f'<div style="background:#0a160a;border:1px solid var(--border);border-radius:6px;'
        f'padding:14px 16px;margin-bottom:14px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;">'
        f'<div style="font-size:11px;color:var(--sub);text-transform:uppercase;letter-spacing:1px;">'
        f'Investimento em bolsas</div>'
        f'<div style="font-size:15px;font-weight:700;color:var(--green);">{_fmt_brl(total_invest)}'
        f'<span style="font-size:10px;color:var(--sub);font-weight:400;"> total acumulado</span></div>'
        f'</div>'
        f'{invest_bars}'
        f'<div style="font-size:10px;color:var(--sub);margin-top:8px;">'
        f'Valores estimados com base nas mensalidades registradas por bolsa no SigPesq. '
        f'Bolsas sem valor cadastrado não são contabilizadas.</div>'
        f'</div>'
    ) if invest_bars else ""

    note = (
        f'De {s["total_with_fellowship"]} formandos com bolsa formal, '
        f'FAPES é a maior financiadora ({s["sponsor_counts"].get("Fapes",0)} alunos), '
        f'seguida por IFES ({s["sponsor_counts"].get("Ifes",0)}) e '
        f'CNPq ({s["sponsor_counts"].get("CNPq",0)}). '
        f'{s["sponsor_counts"].get("Voluntário",0)} participaram voluntariamente '
        f'(PIVIC/PIVITI). {s["multi_bolsa"]} formandos acumularam bolsas de agências distintas.'
    )

    body = (
        f'<div class="grid4" style="margin-bottom:20px;">{cards}</div>'
        f'<div style="background:#0f1a0f;border:1px solid var(--border);'
        f'border-radius:6px;padding:14px 16px;margin-bottom:14px;">'
        f'<div style="font-size:11px;color:var(--sub);margin-bottom:10px;'
        f'text-transform:uppercase;letter-spacing:1px;">Participação relativa — bolsa paga</div>'
        f'{bars_paid}</div>'
        f'{invest_block}'
        f'<div class="note"><strong>Interpretação:</strong> {note}</div>'
    )
    return section(
        "Agências de fomento",
        "Formandos beneficiados por bolsa formal, agrupados pela entidade financiadora",
        body,
    )


def _sec_curso_sponsor(s: dict) -> str:
    AGENCY_COLORS = {
        "Fapes": "var(--amber)", "CNPq": "var(--blue)",
        "Ifes": "var(--green2)", "Voluntário": "var(--sub)",
    }
    sponsor_order = ["Fapes", "Ifes", "CNPq", "Voluntário"]
    cols = ""
    for curso, total_c in sorted(s["curso_total"].items()):
        short = "Eng. Controle e Automação" if "Controle" in curso else "Sistemas de Informação"
        sp = s["curso_sponsor"].get(curso, {})
        max_v = max(sp.values()) if sp else 1
        rows = "".join(
            bar(ag, sp.get(ag, 0), max_v,
                AGENCY_COLORS.get(ag, "var(--sub)"), "md")
            for ag in sponsor_order
            if sp.get(ag, 0) > 0
        )
        cols += (
            f'<div style="background:#0f1a0f;border:1px solid var(--border);'
            f'border-radius:6px;padding:14px;">'
            f'<div style="font-size:12px;font-weight:600;margin-bottom:12px;">{short}</div>'
            f'{rows}</div>'
        )
    body = f'<div class="grid2">{cols}</div>'
    return section(
        "Curso × agência de fomento",
        "Formandos únicos por curso beneficiados por cada agência",
        body,
    )


def _sec_projects_duration(s: dict) -> str:
    pd = s["proj_dist"]
    max_p = max(pd.values()) if pd else 1
    PROJ_COLORS = ["var(--green)", "var(--green2)", "var(--amber)", "var(--amber)", "var(--red)"]
    proj_bars = "".join(
        bar(
            f"{k} projeto{'s' if k > 1 else ''}",
            v, max_p,
            PROJ_COLORS[min(k - 1, len(PROJ_COLORS) - 1)],
            "md",
        )
        for k, v in sorted(pd.items())
    )
    proj_note = (
        f'<div class="note">{s["with_projects"]} formandos com projetos registrados. '
        f'{s["sem_registro"]} sem registro no SigPesq.</div>'
    )
    proj_col = (
        f'<div class="section" style="margin-bottom:0;">'
        f'<h2>Projetos por formando</h2>'
        f'<div class="sub">dentre formandos com projetos registrados</div>'
        f'{proj_bars}{proj_note}</div>'
    )

    # duration
    db = s["dur_bins"]
    total_d = s["durations_n"]
    pct_7_12 = round(db.get("7-12m", 0) / total_d * 100) if total_d else 0
    pct_le6 = round(db.get("≤6m", 0) / total_d * 100) if total_d else 0
    pct_gt12 = round(db.get(">12m", 0) / total_d * 100) if total_d else 0

    dur_col = (
        f'<div class="section" style="margin-bottom:0;">'
        f'<h2>Duração de bolsa</h2>'
        f'<div class="sub">{total_d} registros com data de início/fim</div>'
        f'{bar("7–12 meses", db.get("7-12m",0), total_d, "var(--green)", "md")} '
        f'<span style="font-size:10px;color:var(--sub);">{pct_7_12}%</span>'
        f'{bar("≤ 6 meses", db.get("≤6m",0), total_d, "var(--amber)", "md")} '
        f'<span style="font-size:10px;color:var(--sub);">{pct_le6}%</span>'
        + (f'{bar("> 12 meses", db.get(">12m",0), total_d, "var(--blue)", "md")} '
           f'<span style="font-size:10px;color:var(--sub);">{pct_gt12}%</span>'
           if db.get(">12m", 0) > 0 else "")
        + f'<div class="grid2" style="margin-top:14px;gap:8px;">'
        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:4px;'
        f'padding:10px;text-align:center;">'
        f'<div style="font-size:20px;font-weight:700;color:var(--green);">{s["dur_mean"]}d</div>'
        f'<div style="font-size:10px;color:var(--sub);">média (~{s["dur_mean"]//30} meses)</div></div>'
        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:4px;'
        f'padding:10px;text-align:center;">'
        f'<div style="font-size:20px;font-weight:700;color:var(--green2);">{s["dur_median"]}d</div>'
        f'<div style="font-size:10px;color:var(--sub);">mediana (~{s["dur_median"]//30} meses)</div></div>'
        f'</div></div>'
    )

    return f'<div class="grid2" style="margin-bottom:24px;">{proj_col}{dur_col}</div>'


def _sec_progressao(s: dict) -> str:
    pg = s["prog"]
    cards = "".join(
        f'<div class="prog-card">'
        f'<div class="pt">{label}</div>'
        f'<div class="pn" style="color:{color};">{pg.get(key,0)}</div>'
        f'<div class="ps">{desc}</div>'
        f'</div>'
        for key, label, color, desc in [
            ("vol→pago", "Voluntário → Pago", "var(--green)",
             "iniciaram voluntário, conquistaram bolsa paga"),
            ("multi-agencia", "Multi-agência", "var(--amber)",
             "participaram de projetos financiados por 2 ou mais agências distintas (ex: FAPES em um projeto, CNPq em outro)"),
            ("pago→vol", "Pago → Voluntário", "var(--sub)",
             "tinham bolsa paga, continuaram sem"),
        ]
    )
    note = (
        f'<div class="note" style="border-color:var(--green);margin-top:14px;">'
        f'<strong>Voluntário → Pago:</strong> {pg.get("vol→pago",0)} formandos iniciaram '
        f'a pesquisa sem remuneração (PIVIC voluntário) e, em projetos subsequentes, '
        f'conquistaram bolsa paga — indicador de progressão na carreira de pesquisa.'
        f'<br><br>'
        f'<strong>Multi-agência:</strong> {pg.get("multi-agencia",0)} formandos '
        f'participaram de projetos financiados por agências diferentes ao longo da graduação — '
        f'por exemplo, uma bolsa FAPES em iniciação científica e outra CNPq em projeto distinto. '
        f'Isso reflete diversificação de vínculos de pesquisa, não acúmulo simultâneo de bolsas.'
        f'</div>'
    )
    return section(
        "Progressão de bolsa",
        f"Trajetória de formandos com múltiplas bolsas — {s['multi_bolsa']} com 2+ bolsas",
        f'<div class="grid3">{cards}</div>{note}',
    )


def _sec_orientadores(s: dict) -> str:
    sd = s["sup_dist"]
    max_sd = max(sd.values()) if sd else 1
    dist_bars = "".join(
        bar(
            f"{k} orientador{'es' if k > 1 else ''}",
            v, max_sd, "var(--green)" if k == 1 else ("var(--amber)" if k == 2 else "var(--red)"),
            "md",
        )
        for k, v in sorted(sd.items())
    )
    multi = sum(v for k, v in sd.items() if k > 1)
    dist_note = (
        f'<div style="margin-top:10px;font-size:11px;color:var(--sub);">'
        f'{multi} formandos ({round(multi/sum(sd.values())*100) if sd else 0}%) '
        f'atuaram com múltiplos orientadores.</div>'
    )

    top_rows = "".join(
        f'<div class="list-row"><span style="color:var(--text);">{name}</span>'
        f'<span style="color:var(--green);font-weight:600;">{count}</span></div>'
        for name, count in s["top_sups"][:8]
    )

    body = (
        f'<div class="grid2">'
        f'<div>{dist_bars}{dist_note}</div>'
        f'<div><div style="font-size:11px;color:var(--sub);margin-bottom:8px;'
        f'text-transform:uppercase;letter-spacing:1px;">Top orientadores</div>'
        f'{top_rows}</div>'
        f'</div>'
    )
    return section(
        "Orientadores por formando",
        "Formandos que tiveram mais de um orientador ao longo do curso",
        body,
    )


def _sec_rg(s: dict) -> str:
    rg_top = s["rg_top"]
    if not rg_top:
        return ""
    max_v = rg_top[0][1] if rg_top else 1
    rows = "".join(bar(name[:50], count, max_v, "var(--green2)") for name, count in rg_top)
    return section("Grupos de pesquisa", "formandos vinculados a grupos", rows)


def _sec_ka(s: dict) -> str:
    ka = s["ka_top"]
    if not ka:
        return ""
    max_v = ka[0][1] if ka else 1
    COLORS = {0: "var(--green)", 1: "var(--green)", 2: "var(--green2)",
              3: "var(--amber)", 4: "var(--amber)", 5: "var(--blue)"}
    rows = "".join(
        bar(name[:40], count, max_v, COLORS.get(i, "var(--sub)"))
        for i, (name, count) in enumerate(ka)
    )
    note = (
        '<div class="note">KAs derivadas dos grupos de pesquisa vinculados — '
        'não dos currículos individuais. Formandos são cadastrados como estudantes '
        'e não possuem currículo Lattes indexado no SigPesq.</div>'
    )
    return section(
        "Áreas de conhecimento",
        "Derivado dos grupos de pesquisa aos quais formandos estiveram vinculados",
        rows + note,
    )


def _sec_artigos() -> str:
    body = (
        f'<div style="display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start;">'
        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:8px;'
        f'padding:20px 28px;text-align:center;">'
        f'<div style="font-size:40px;font-weight:700;color:var(--sub);">0</div>'
        f'<div style="font-size:11px;color:var(--sub);">artigos</div>'
        f'</div>'
        f'<div class="note" style="margin-top:0;">'
        f'<strong>Por que zero?</strong><br>'
        f'O campo <code>articles</code> é populado via extração do currículo Lattes — '
        f'disponível apenas para docentes e pesquisadores com Lattes vinculado. '
        f'Formandos são cadastrados como estudantes e não têm Lattes indexado no SigPesq. '
        f'Co-autorias existem mas não são acessíveis sem cruzar DOIs via API externa.<br><br>'
        f'<span style="color:var(--amber);">→ Para medir produção discente, indexar os '
        f'Lattes dos estudantes ou cruzar DOIs via API.</span>'
        f'</div></div>'
    )
    return section("Produção científica", "Artigos registrados para formandos no sistema", body)


def _sec_ic_timing(s: dict) -> str:
    t = s.get("ic_timing", {})
    if not t or not t.get("period_dist"):
        return ""

    avg = t["avg_semesters"]
    n = t["n_with_entry"]
    pd = t["period_dist"]
    yd = t["year_dist"]

    max_pd = max(pd.values()) if pd else 1
    max_yd = max(yd.values()) if yd else 1

    # -- KPI cards --
    early = sum(v for k, v in pd.items() if k <= 2)
    mid   = sum(v for k, v in pd.items() if 3 <= k <= 5)
    late  = sum(v for k, v in pd.items() if k >= 6)

    kpi_cards = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">'

        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--green);">{avg}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">semestres médios<br>até 1ª IC</div>'
        f'</div>'

        f'<div style="background:#0d1a0d;border:1px solid var(--green);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--green);">{early}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">iniciaram cedo<br>(1º–2º semestre)</div>'
        f'</div>'

        f'<div style="background:#0d1a0d;border:1px solid var(--amber);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--amber);">{mid}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">período intermediário<br>(3º–5º semestre)</div>'
        f'</div>'

        f'<div style="background:#0d1a0d;border:1px solid var(--sub);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--sub);">{late}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">iniciaram tarde<br>(6º semestre ou mais)</div>'
        f'</div>'

        f'</div>'
    )

    # -- Period distribution bars --
    COURSE_LEN = {"Sistemas de Informação": 8, "Engenharia de Controle e Automação": 10}
    default_len = 8

    def _period_color(k: int) -> str:
        if k <= 2:
            return "var(--green)"
        if k <= 5:
            return "var(--amber)"
        return "var(--sub)"

    period_bars = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
        f'<span style="font-size:11px;color:var(--text);width:70px;flex-shrink:0;">{k}º semestre</span>'
        f'<div style="flex:1;height:14px;background:#1a2a1a;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{round(v/max_pd*100)}%;height:100%;background:{_period_color(k)};"></div>'
        f'</div>'
        f'<span style="font-size:11px;font-weight:600;color:{_period_color(k)};width:24px;text-align:right;">{v}</span>'
        f'</div>'
        for k, v in sorted(pd.items())
    )

    # -- Year distribution bars --
    year_bars = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
        f'<span style="font-size:11px;color:var(--text);width:40px;flex-shrink:0;">{yr}</span>'
        f'<div style="flex:1;height:12px;background:#1a2a1a;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{round(v/max_yd*100)}%;height:100%;background:var(--blue);"></div>'
        f'</div>'
        f'<span style="font-size:11px;color:var(--blue);width:20px;text-align:right;">{v}</span>'
        f'</div>'
        for yr, v in sorted(yd.items())
    )

    charts = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:16px;">'

        f'<div><div style="font-size:11px;color:var(--sub);text-transform:uppercase;'
        f'letter-spacing:.05em;margin-bottom:10px;">Semestre do curso na 1ª IC</div>'
        f'{period_bars}</div>'

        f'<div><div style="font-size:11px;color:var(--sub);text-transform:uppercase;'
        f'letter-spacing:.05em;margin-bottom:10px;">Ano de início (calendário)</div>'
        f'{year_bars}</div>'

        f'</div>'
    )

    note = (
        f'<div class="note" style="margin-top:0;">'
        f'<strong>Metodologia:</strong> período calculado pela diferença entre semestre de entrada '
        f'(extraído da matrícula — ex: <code>20181BSI…</code> → 2018/1) e data de início do '
        f'primeiro projeto SigPesq. Base: {n} de {s["with_research"]} formandos com pesquisa '
        f'e matrícula interpretável. '
        f'<span style="color:var(--green);">Verde = 1º–2º sem.</span> · '
        f'<span style="color:var(--amber);">Âmbar = 3º–5º sem.</span> · '
        f'<span style="color:var(--sub);">Cinza = 6º sem.+</span>'
        f'</div>'
    )

    return section(
        "Quando os formandos entraram na IC",
        f"Tempo entre matrícula e 1ª iniciação científica — média: {avg} semestres · base: {n} formandos",
        kpi_cards + charts + note,
    )


def _sec_lattes_cross(s: dict) -> str:
    lc = s.get("lattes_cross")
    if not lc:
        return ""

    sp_n = lc["sigpesq_n"]
    union_n = lc["union_n"]
    avg_sp = lc["avg_sigpesq"]
    avg_un = lc["avg_union"]
    delta = lc["delta_avg"]
    delta_pct = lc["delta_pct"]
    enriched = lc["enriched_count"]
    new_names = lc["new_via_lattes"]
    ic_form = lc["lattes_ic_formandos"]
    tcc_form = lc["lattes_tcc_formandos"]

    delta_color = "var(--green)" if delta >= 0 else "#e05252"

    # Comparison table
    table_rows = f"""
      <tr>
        <td>Formandos com pesquisa (SigPesq)</td>
        <td style="text-align:right;font-weight:600;">{sp_n}</td>
        <td style="text-align:right;font-weight:600;">{lc['coverage_sigpesq_pct']}%</td>
      </tr>
      <tr>
        <td>Formandos com pesquisa (SigPesq + Lattes)</td>
        <td style="text-align:right;font-weight:600;">{union_n}</td>
        <td style="text-align:right;font-weight:600;">{lc['coverage_union_pct']}%</td>
      </tr>
      <tr>
        <td>Formandos IC via Lattes</td>
        <td style="text-align:right;">{ic_form}</td>
        <td></td>
      </tr>
      <tr>
        <td>Formandos TCC via Lattes</td>
        <td style="text-align:right;">{tcc_form}</td>
        <td></td>
      </tr>
      <tr>
        <td>Média projetos/formando — SigPesq</td>
        <td style="text-align:right;font-weight:600;">{avg_sp}</td>
        <td></td>
      </tr>
      <tr>
        <td>Média projetos/formando — União</td>
        <td style="text-align:right;font-weight:600;color:{delta_color};">{avg_un}</td>
        <td style="text-align:right;color:{delta_color};">+{delta_pct}%</td>
      </tr>
      <tr>
        <td>Formandos enriquecidos (Lattes adicionou TCC)</td>
        <td style="text-align:right;">{enriched}</td>
        <td></td>
      </tr>
    """

    comparison_table = (
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead><tr>'
        f'<th style="text-align:left;padding:8px 4px;border-bottom:1px solid var(--border);">Métrica</th>'
        f'<th style="text-align:right;padding:8px 4px;border-bottom:1px solid var(--border);">Valor</th>'
        f'<th style="text-align:right;padding:8px 4px;border-bottom:1px solid var(--border);">%</th>'
        f'</tr></thead><tbody>{table_rows}</tbody></table>'
    )

    # Distribution bars: SigPesq vs Union
    all_counts = sorted(set(lc["sp_dist"]) | set(lc["union_dist"]))
    max_val = max(
        max(lc["sp_dist"].values(), default=1),
        max(lc["union_dist"].values(), default=1),
    )
    dist_rows = ""
    for c in all_counts:
        sp_v = lc["sp_dist"].get(c, 0)
        un_v = lc["union_dist"].get(c, 0)
        sp_w = round(sp_v / max_val * 120)
        un_w = round(un_v / max_val * 120)
        dist_rows += (
            f'<tr style="border-bottom:1px solid var(--border);">'
            f'<td style="padding:5px 8px;font-weight:600;">{c}×</td>'
            f'<td style="padding:5px 8px;">'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<div style="width:{sp_w}px;height:10px;background:var(--sub);border-radius:2px;"></div>'
            f'<span style="font-size:12px;">{sp_v}</span></div></td>'
            f'<td style="padding:5px 8px;">'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<div style="width:{un_w}px;height:10px;background:var(--green);border-radius:2px;"></div>'
            f'<span style="font-size:12px;">{un_v}</span></div></td>'
            f'</tr>'
        )

    dist_table = (
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead><tr>'
        f'<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">Projetos</th>'
        f'<th style="padding:6px 8px;border-bottom:1px solid var(--border);">SigPesq</th>'
        f'<th style="padding:6px 8px;border-bottom:1px solid var(--border);">SigPesq + Lattes</th>'
        f'</tr></thead><tbody>{dist_rows}</tbody></table>'
    )

    # New formandos discovered via Lattes
    new_list = ""
    if new_names:
        items = "".join(f'<li style="margin:2px 0;">{n}</li>' for n in new_names[:20])
        suffix = f'<li style="color:var(--sub);">... e mais {len(new_names)-20}</li>' if len(new_names) > 20 else ""
        new_list = (
            f'<div style="margin-top:20px;">'
            f'<div style="font-size:12px;font-weight:600;color:var(--sub);text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:8px;">Formandos novos via Lattes ({len(new_names)})</div>'
            f'<ul style="margin:0;padding-left:20px;font-size:13px;columns:2;gap:24px;">'
            f'{items}{suffix}</ul></div>'
        )

    body = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start;">'
        f'<div>{comparison_table}</div>'
        f'<div>{dist_table}</div>'
        f'</div>'
        f'{new_list}'
        f'<div class="note" style="margin-top:20px;">'
        f'<strong>Metodologia:</strong> SigPesq registra bolsas IC/IT com orientador. '
        f'Lattes captura adicionalmente TCCs (não registrados no SigPesq) e IC informais. '
        f'IC duplicada entre fontes toma o maior contagem individual (max). '
        f'TCC é aditivo — SigPesq não rastreia. '
        f'Impacto: média sobe de <strong>{avg_sp}</strong> → <strong style="color:{delta_color};">{avg_un}</strong> proj/formando '
        f'(<strong style="color:{delta_color};">+{delta_pct}%</strong>).'
        f'</div>'
    )

    return section(
        "Cruzamento Lattes × SigPesq",
        "Impacto do Lattes na cobertura de projetos por formando",
        body,
    )


def _sec_graduation_time(s: dict) -> str:
    gt = s.get("graduation_time", {})
    overall = gt.get("overall", {})
    by_curso = gt.get("by_curso", {})
    cats = gt.get("categories", {})
    if not overall:
        return ""

    mean_sem = overall["mean"]
    median_sem = overall["median"]
    n = overall["n"]
    total = s["total"]
    n_transfers = cats.get("transfers", 0)
    n_regular   = cats.get("regular", 0)
    n_extended  = cats.get("extended", 0)

    kpi = (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;">'
        f'<div style="background:#0d1a0d;border:1px solid var(--green);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--green);">{mean_sem}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">semestres médios<br>({mean_sem / 2:.1f} anos)</div>'
        f'</div>'
        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--green2);">{median_sem}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">mediana<br>({median_sem / 2:.1f} anos)</div>'
        f'</div>'
        f'<div style="background:#0d1a0d;border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:700;color:var(--sub);">{n}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:4px;">formandos<br>com matrícula interpretável</div>'
        f'</div>'
        f'</div>'
    )

    # Category breakdown row
    cat_row = (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;">'

        f'<div style="background:#0a160a;border:1px solid var(--blue);border-radius:6px;padding:12px;text-align:center;">'
        f'<div style="font-size:22px;font-weight:700;color:var(--blue);">{n_transfers}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">Ingresso acelerado<br>'
        f'<span style="color:var(--blue);">&lt; 4 semestres</span></div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">provável transferência ou aproveitamento</div>'
        f'</div>'

        f'<div style="background:#0a160a;border:1px solid var(--green);border-radius:6px;padding:12px;text-align:center;">'
        f'<div style="font-size:22px;font-weight:700;color:var(--green);">{n_regular}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">Tempo regular<br>'
        f'<span style="color:var(--green);">4–24 semestres</span></div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">faixa esperada do currículo</div>'
        f'</div>'

        f'<div style="background:#0a160a;border:1px solid var(--amber);border-radius:6px;padding:12px;text-align:center;">'
        f'<div style="font-size:22px;font-weight:700;color:var(--amber);">{n_extended}</div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">Graduação prolongada<br>'
        f'<span style="color:var(--amber);">&gt; 24 semestres</span></div>'
        f'<div style="font-size:10px;color:var(--sub);margin-top:3px;">provável trancamento prolongado</div>'
        f'</div>'

        f'</div>'
    )

    curso_blocks = ""
    by_curso_cats = gt.get("by_curso_categories", {})
    for curso, cstats in sorted(by_curso.items()):
        if not cstats:
            continue
        short = "ECA" if "Controle" in curso else "SI"
        expected = 10 if "Controle" in curso else 8
        cc = by_curso_cats.get(curso, {})
        dist = cstats.get("dist", {})
        max_dist = max(dist.values()) if dist else 1

        def _bar_color(k: int) -> str:
            if k < 4:
                return "var(--blue)"
            if k <= expected + 2:
                return "var(--green)"
            if k <= 24:
                return "var(--amber)"
            return "var(--red)"

        dist_bars = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">'
            f'<span style="font-size:10px;color:{_bar_color(k)};width:50px;flex-shrink:0;">{k} sem</span>'
            f'<div style="flex:1;height:10px;background:#1a2a1a;border-radius:2px;overflow:hidden;">'
            f'<div style="width:{round(v / max_dist * 100)}%;height:100%;background:{_bar_color(k)};"></div>'
            f'</div>'
            f'<span style="font-size:10px;color:var(--sub);width:20px;text-align:right;">{v}</span>'
            f'</div>'
            for k, v in sorted(dist.items())
        )
        cat_summary = ""
        if cc.get("transfers"):
            cat_summary += f' · <span style="color:var(--blue);">{cc["transfers"]} acelerado</span>'
        if cc.get("extended"):
            cat_summary += f' · <span style="color:var(--red);">{cc["extended"]} prolongado</span>'
        curso_blocks += (
            f'<div style="background:#0f1a0f;border:1px solid var(--border);border-radius:6px;padding:14px;">'
            f'<div style="font-size:12px;font-weight:600;margin-bottom:4px;">{short}</div>'
            f'<div style="font-size:11px;color:var(--sub);margin-bottom:10px;">'
            f'média {cstats["mean"]} sem ({cstats["mean"] / 2:.1f} anos) · '
            f'mediana {cstats["median"]} sem · n={cstats["n"]}'
            f'{cat_summary}</div>'
            f'{dist_bars}</div>'
        )

    # ---- IC vs sem-IC comparison card ----
    icv = gt.get("ic_vs_no_ic", {})
    ic_stats  = icv.get("ic", {})
    no_stats  = icv.get("no_ic", {})
    icv_curso = icv.get("by_curso", {})

    def _fmt(st: dict, key: str) -> str:
        v = st.get(key)
        return f"{v}" if v is not None else "—"

    def _delta_str(ic_val, no_val) -> str:
        if ic_val is None or no_val is None:
            return ""
        d = round(ic_val - no_val, 1)
        color = "var(--green)" if d <= 0 else "var(--amber)"
        sign = "+" if d > 0 else ""
        return f'<span style="color:{color};font-size:10px;"> ({sign}{d})</span>'

    def _row(label: str, ic_st: dict, no_st: dict, key: str) -> str:
        iv = ic_st.get(key)
        nv = no_st.get(key)
        return (
            f'<tr style="border-bottom:1px solid var(--border);">'
            f'<td style="padding:7px 10px;font-size:12px;color:var(--sub);">{label}</td>'
            f'<td style="padding:7px 10px;font-size:13px;font-weight:600;color:var(--green);text-align:center;">'
            f'{_fmt(ic_st, key)}{_delta_str(iv, nv)}</td>'
            f'<td style="padding:7px 10px;font-size:13px;color:var(--sub);text-align:center;">'
            f'{_fmt(no_st, key)}</td>'
            f'</tr>'
        )

    def _section_rows(label: str, ic_st: dict, no_st: dict) -> str:
        header = (
            f'<tr style="background:#0a160a;">'
            f'<td colspan="3" style="padding:6px 10px;font-size:11px;font-weight:700;'
            f'color:var(--text);text-transform:uppercase;letter-spacing:.05em;">{label}</td>'
            f'</tr>'
        )
        return header + _row("Média (sem)", ic_st, no_st, "mean") + _row("Mediana (sem)", ic_st, no_st, "median")

    table_rows = _section_rows("Geral", ic_stats, no_stats)
    for curso, cv in sorted(icv_curso.items()):
        short = "ECA — Eng. Controle e Automação" if "Controle" in curso else "SI — Sistemas de Informação"
        table_rows += _section_rows(short, cv.get("ic", {}), cv.get("no_ic", {}))

    ic_n  = ic_stats.get("n", 0)
    no_n  = no_stats.get("n", 0)
    ic_table = (
        f'<div style="background:#0a160a;border:1px solid var(--border);border-radius:8px;'
        f'overflow:hidden;margin-bottom:16px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="border-bottom:2px solid var(--border);">'
        f'<th style="padding:10px;text-align:left;font-size:12px;color:var(--sub);">Grupo</th>'
        f'<th style="padding:10px;text-align:center;font-size:12px;color:var(--green);">'
        f'Com IC <span style="font-weight:400;">({ic_n})</span></th>'
        f'<th style="padding:10px;text-align:center;font-size:12px;color:var(--sub);">'
        f'Sem IC <span style="font-weight:400;">({no_n})</span></th>'
        f'</tr></thead>'
        f'<tbody>{table_rows}</tbody>'
        f'</table>'
        f'<div style="padding:8px 10px;font-size:10px;color:var(--sub);">'
        f'Delta (verde) = alunos com IC formam mais rápido que sem IC.'
        f'</div>'
        f'</div>'
    )

    # ---- interpretive insight block ----
    ic_mean = ic_stats.get("mean")
    no_mean = no_stats.get("mean")
    ic_med  = ic_stats.get("median")
    no_med  = no_stats.get("median")

    if ic_mean is not None and no_mean is not None:
        delta_m   = round(ic_mean - no_mean, 1)
        abs_dm    = abs(delta_m)
        negligible_overall = abs_dm < 1.0

        # per-course deltas
        curso_deltas: list[dict] = []
        for curso, cv in sorted(icv_curso.items()):
            ic_c = cv.get("ic", {})
            no_c = cv.get("no_ic", {})
            ic_cm = ic_c.get("mean")
            no_cm = no_c.get("mean")
            ic_cmed = ic_c.get("median")
            no_cmed = no_c.get("median")
            if ic_cm is not None and no_cm is not None:
                d = round(ic_cm - no_cm, 1)
                curso_deltas.append({
                    "short": "ECA" if "Controle" in curso else "SI",
                    "ic_mean": ic_cm, "no_mean": no_cm,
                    "ic_med": ic_cmed, "no_med": no_cmed,
                    "delta": d, "n_ic": ic_c.get("n", 0), "n_no": no_c.get("n", 0),
                })

        # detect masking: any course with |delta| >= 3 AND opposite sign to overall
        masking_courses = [
            c for c in curso_deltas
            if abs(c["delta"]) >= 3 and (
                (negligible_overall) or
                (delta_m > 0 and c["delta"] < 0) or
                (delta_m < 0 and c["delta"] > 0)
            )
        ]
        strongest = max(curso_deltas, key=lambda c: abs(c["delta"])) if curso_deltas else None

        # ---- headline based on overall ----
        if negligible_overall:
            headline = "No agregado, IC não altera o tempo de formação — mas o dado por curso conta outra história"
            headline_color = "var(--amber)"
        elif delta_m < 0:
            headline = f"Alunos com IC se formam mais rápido — {abs_dm} semestre{'s' if abs_dm != 1 else ''} a menos no geral"
            headline_color = "var(--green)"
        else:
            headline = f"Alunos com IC levam {abs_dm} semestre{'s' if abs_dm != 1 else ''} a mais no geral"
            headline_color = "var(--amber)"

        # ---- overall paragraph ----
        _delta_color_overall = "var(--green)" if delta_m <= 0 else "var(--amber)"
        _delta_sign = "−" if delta_m < 0 else "+"
        _delta_plural = "s" if abs_dm != 1 else ""
        overall_text = (
            f"No total, formandos com IC levaram em média <strong>{ic_mean} semestres</strong> "
            f"({ic_mean / 2:.1f} anos) para concluir o curso, contra <strong>{no_mean} semestres</strong> "
            f"({no_mean / 2:.1f} anos) dos sem IC — diferença de "
            f"<strong style='color:{_delta_color_overall};'>"
            f"{_delta_sign}{abs_dm} semestre{_delta_plural}</strong>. "
            f"A mediana segue o mesmo padrão: {ic_med} sem (com IC) vs {no_med} sem (sem IC)."
        )

        # ---- per-course paragraphs ----
        curso_paras = ""
        for c in curso_deltas:
            d = c["delta"]
            abs_d = abs(d)
            d_color = "var(--green)" if d <= -1 else ("var(--amber)" if d >= 1 else "var(--sub)")
            d_anos = abs(d) / 2
            if abs_d < 1:
                verdict = "sem diferença relevante"
                verdict_detail = (
                    f"Com IC: {c['ic_mean']} sem · Sem IC: {c['no_mean']} sem "
                    f"(delta {'−' if d < 0 else '+'}{abs_d} sem — dentro da margem de variação normal)."
                )
            elif d < 0:
                verdict = f"com IC {abs_d} semestres mais rápido ({d_anos:.1f} anos a menos)"
                verdict_detail = (
                    f"Média com IC: <strong>{c['ic_mean']} sem</strong> ({c['ic_mean'] / 2:.1f} anos) · "
                    f"Sem IC: <strong>{c['no_mean']} sem</strong> ({c['no_mean'] / 2:.1f} anos). "
                    f"Mediana: {c['ic_med']} vs {c['no_med']} sem. Base: {c['n_ic']} com IC, {c['n_no']} sem IC."
                )
            else:
                verdict = f"com IC {abs_d} semestres mais lento ({d_anos:.1f} anos a mais)"
                verdict_detail = (
                    f"Média com IC: <strong>{c['ic_mean']} sem</strong> ({c['ic_mean'] / 2:.1f} anos) · "
                    f"Sem IC: <strong>{c['no_mean']} sem</strong> ({c['no_mean'] / 2:.1f} anos). "
                    f"Mediana: {c['ic_med']} vs {c['no_med']} sem. Base: {c['n_ic']} com IC, {c['n_no']} sem IC."
                )
            curso_paras += (
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:4px;">'
                f'{c["short"]} — <span style="color:{d_color};">{verdict}</span></div>'
                f'<p style="font-size:12px;color:var(--sub);line-height:1.6;margin:0;">{verdict_detail}</p>'
                f'</div>'
            )

        # ---- masking warning ----
        masking_block = ""
        if masking_courses and negligible_overall:
            names = " e ".join(c["short"] for c in masking_courses)
            s_strongest = masking_courses[0]
            masking_block = (
                f'<div style="background:#1a1400;border:1px solid var(--amber);border-radius:6px;'
                f'padding:12px 14px;margin:12px 0;font-size:12px;line-height:1.6;">'
                f'<strong style="color:var(--amber);">⚠ Efeito de agregação:</strong> '
                f'a média geral ({delta_m:+} sem) oculta diferenças expressivas por curso. '
                f'No {names}, o delta chega a '
                f'<strong style="color:var(--amber);">{s_strongest["delta"]:+} semestres</strong> — '
                f'o agregado não é representativo de nenhum dos cursos individualmente.'
                f'</div>'
            )

        # ---- interpretation ----
        if strongest and abs(strongest["delta"]) >= 3 and strongest["delta"] < 0:
            takeaway = (
                f"O dado mais relevante está no {strongest['short']}: alunos que participaram de IC "
                f"concluíram o curso <strong>{abs(strongest['delta'])} semestres mais cedo</strong> "
                f"({abs(strongest['delta']) / 2:.1f} anos) do que os que não participaram. "
                f"Uma hipótese plausível é o <em>efeito de ancoragem</em>: a IC cria vínculo institucional, "
                f"reduz evasão e trancamentos, e mantém o aluno em progressão regular. "
                f"Alunos sem IC no {strongest['short']} apresentam média de {strongest['no_mean']} semestres "
                f"— muito acima do mínimo curricular de {'10' if strongest['short'] == 'ECA' else '8'} semestres — "
                f"sugerindo alta taxa de interrupções nesse grupo. "
                f"Importante: correlação não implica causalidade. Pode haver seleção — "
                f"alunos mais engajados ingressam em IC <em>e</em> terminam mais rápido."
            )
        elif negligible_overall:
            takeaway = (
                "IC não representa risco para a conclusão do curso em nenhum dos cursos analisados. "
                "Onde a diferença existe, favorece os alunos com IC. "
                "O dado sugere que conciliar pesquisa e graduação é viável, e possivelmente benéfico."
            )
        else:
            takeaway = (
                "IC não é fator de atraso. A diferença observada, quando existe, pode refletir "
                "perfil de aluno ou trajetória acadêmica mais intensa — não um custo imposto pela pesquisa."
            )

        insight_block = (
            f'<div style="background:#0b1a0b;border:1px solid var(--border);border-left:4px solid {headline_color};'
            f'border-radius:8px;padding:18px 20px;margin-bottom:16px;">'
            f'<div style="font-size:14px;font-weight:700;color:{headline_color};margin-bottom:12px;">'
            f'{headline}</div>'
            f'<p style="font-size:13px;color:var(--text);line-height:1.7;margin-bottom:14px;">{overall_text}</p>'
            f'{masking_block}'
            f'<div style="border-top:1px solid var(--border);padding-top:14px;margin-bottom:12px;">'
            f'<div style="font-size:11px;color:var(--sub);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;">Por curso</div>'
            f'{curso_paras}</div>'
            f'<div style="border-top:1px solid var(--border);padding-top:12px;">'
            f'<p style="font-size:12px;color:var(--sub);line-height:1.6;margin:0;">'
            f'<strong style="color:var(--text);">Interpretação:</strong> {takeaway}</p>'
            f'</div>'
            f'</div>'
        )
    else:
        insight_block = ""

    note = (
        f'<div class="note">'
        f'<strong>Metodologia:</strong> tempo calculado em semestres entre entrada (extraída da matrícula '
        f'— ex: <code>20181BSI…</code> → 2018/1) e semestre de formatura. '
        f'Mínimo curricular: SI = 8 semestres, ECA = 10 semestres. '
        f'Acelerado (&lt;4 sem): provável transferência ou aproveitamento de disciplinas. '
        f'Prolongado (&gt;24 sem): provável trancamento ou reingresso. '
        f'Base: {n} de {total} formandos com matrícula interpretável.'
        f'</div>'
    )

    body = kpi + cat_row + ic_table + insight_block + f'<div class="grid2" style="margin-bottom:16px;">{curso_blocks}</div>' + note
    return section(
        "Tempo de formação",
        f"Semestres do ingresso até a colação — geral: média {mean_sem} sem ({mean_sem / 2:.1f} anos) · base: {n} formandos",
        body,
    )


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def render_html(s: dict, semester: str, generated_at: str) -> str:
    sem_label = semester.replace("_", ".")
    body_parts = [
        _sec_stats(s),
        _sec_curso(s),
        _sec_fellowship(s),
        _sec_agencies(s),
        _sec_curso_sponsor(s),
        _sec_projects_duration(s),
        _sec_progressao(s),
        _sec_orientadores(s),
        _sec_rg(s),
        _sec_ka(s),
        _sec_artigos(),
        _sec_graduation_time(s),
        _sec_ic_timing(s),
        _sec_lattes_cross(s),
    ]
    body = "\n".join(p for p in body_parts if p)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Formandos × Pesquisa — IFES Serra {sem_label}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="eyebrow">IFES Serra · Relatório de Pesquisa</div>
  <h1>Formandos × Pesquisa — {sem_label}</h1>
  <p>Análise da participação em iniciação científica e tecnológica dos formandos do semestre {sem_label}.</p>
</header>
{body}
<footer>Gerado em {generated_at} · fonte: SigPesq / exportações canônicas</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semester", default="2024_1",
                        choices=list(SEMESTER_FILE_MAP.keys()))
    parser.add_argument("--out", default=None,
                        help="Output HTML path (default: data/exports/formandos/)")
    args = parser.parse_args()

    print(f"Loading formandos for {args.semester}...")
    formandos = load_formandos(args.semester)
    print(f"  {len(formandos)} formandos")

    print("Loading exports...")
    adv_projects = load_json("advisorships_canonical.json")
    rgs = load_json("research_groups_canonical.json")

    print("Loading Lattes CVs...")
    lattes = load_lattes()
    print(f"  {len(lattes['ic'])} IC records, {len(lattes['tcc'])} TCC records")

    print("Computing statistics...")
    stats = compute(formandos, adv_projects, rgs, lattes=lattes, grad_semester=args.semester)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = render_html(stats, args.semester, now)

    out_path = (
        Path(args.out)
        if args.out
        else OUT_DIR / f"formandos_pesquisa_{args.semester}_generated.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
