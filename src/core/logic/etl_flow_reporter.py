import json
import sqlite3
import time
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError

from src.adapters.sources.lattes_parser import LattesParser
from src.core.logic.duplicate_auditor import DuplicateAuditor
from src.tracking.recorder import tracking_recorder

TRACKED_TABLES = [
    "persons",
    "researchers",
    "person_emails",
    "organizations",
    "organizational_units",
    "initiative_types",
    "initiatives",
    "advisorships",
    "fellowships",
    "articles",
    "article_authors",
    "academic_educations",
    "teams",
    "team_members",
    "research_groups",
    "knowledge_areas",
    "researcher_knowledge_areas",
    "initiative_teams",
]
TRACKING_TABLES = [
    "ingestion_runs",
    "source_records",
    "entity_matches",
    "attribute_assertions",
    "entity_change_logs",
]
CNPQ_PLACEHOLDER_PERSON_NAMES = ("ui-button",)


def _safe_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _snapshot_tables(db_path: str) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {table: _safe_count(conn, table) for table in TRACKED_TABLES}


def _has_tracking_schema(db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        table_names = {row[0] for row in rows}
    return all(table in table_names for table in TRACKING_TABLES)


def _duplicate_summary(db_path: str) -> dict[str, int]:
    report = DuplicateAuditor(db_path).run()
    return {key: len(value) for key, value in report.items()}


def _tracking_summary(db_path: str) -> dict[str, Any]:
    if not _has_tracking_schema(db_path):
        return {
            "enabled": False,
            "note": "Tracking tables not found in current database.",
        }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        totals = {table: _safe_count(conn, table) for table in TRACKING_TABLES}
        latest_runs = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, source_system, flow_name, status, started_at, finished_at
                FROM ingestion_runs
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
        ]
    return {
        "enabled": True,
        "totals": totals,
        "latest_runs": latest_runs,
    }


def _step_warnings(
    *,
    origin: str | None,
    before_duplicates: dict[str, int],
    after_duplicates: dict[str, int],
) -> list[dict[str, Any]]:
    warnings = []
    for metric, after_count in after_duplicates.items():
        before_count = before_duplicates.get(metric, 0)
        if after_count <= before_count:
            continue
        warnings.append(
            {
                "source": origin or "unknown",
                "severity": "warning",
                "code": "duplicate_count_increased",
                "metric": metric,
                "before": before_count,
                "after": after_count,
                "count": after_count - before_count,
                "message": (
                    f"Duplicate groups for {metric} increased from "
                    f"{before_count} to {after_count}."
                ),
            }
        )
    return warnings


def _result_warnings(result: Any, *, default_source: str) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    warnings: list[dict[str, Any]] = []
    for warning in result.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        warning = dict(warning)
        warning.setdefault("source", default_source)
        warnings.append(warning)

    for source, source_warnings in (result.get("warnings_by_source") or {}).items():
        for warning in source_warnings or []:
            if not isinstance(warning, dict):
                continue
            warning = dict(warning)
            warning.setdefault("source", source)
            warnings.append(warning)

    return warnings


def _warnings_by_source(
    *,
    db_path: str,
    steps: list[dict[str, Any]],
    final_duplicates: dict[str, int],
    tracking_summary: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    warnings: dict[str, list[dict[str, Any]]] = {}

    for step in steps:
        for warning in step.get("warnings") or []:
            source = warning.get("source") or step.get("origin") or "unknown"
            warnings.setdefault(source, []).append(
                {key: value for key, value in warning.items() if key != "source"}
            )

    for warning in _cnpq_data_quality_warnings(db_path):
        warnings.setdefault("cnpq", []).append(warning)

    duplicate_warnings = _duplicate_data_quality_warnings(final_duplicates)
    if duplicate_warnings:
        warnings.setdefault("duplicate_audit", []).extend(duplicate_warnings)

    tracking_warnings = _tracking_data_quality_warnings(tracking_summary)
    if tracking_warnings:
        warnings.setdefault("tracking", []).extend(tracking_warnings)

    return {source: rows for source, rows in sorted(warnings.items()) if rows}


def _cnpq_data_quality_warnings(db_path: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "persons"):
            return []

        placeholders = [name.lower() for name in CNPQ_PLACEHOLDER_PERSON_NAMES]
        query_marks = ", ".join("?" for _ in placeholders)
        rows = conn.execute(
            f"""
            SELECT name, COUNT(*) AS count
            FROM persons
            WHERE lower(trim(name)) IN ({query_marks})
            GROUP BY name
            ORDER BY count DESC, name
            """,
            placeholders,
        ).fetchall()

    if not rows:
        return []

    total = sum(row["count"] for row in rows)
    examples = [row["name"] for row in rows[:5]]
    return [
        {
            "severity": "warning",
            "code": "cnpq_placeholder_member_name",
            "count": total,
            "examples": examples,
            "message": (
                "CNPq member extraction produced placeholder person names; "
                "inspect crawler selectors before using these people as real members."
            ),
        }
    ]


def _duplicate_data_quality_warnings(
    final_duplicates: dict[str, int],
) -> list[dict[str, Any]]:
    warnings = []
    for metric, count in final_duplicates.items():
        if count <= 0:
            continue
        warnings.append(
            {
                "severity": "warning",
                "code": "duplicate_count_present",
                "metric": metric,
                "count": count,
                "message": f"{count} duplicate group(s) remain for {metric}.",
            }
        )
    return warnings


def _tracking_data_quality_warnings(
    tracking_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if not tracking_summary.get("enabled"):
        return []

    failed_runs = [
        row
        for row in tracking_summary.get("latest_runs", [])
        if str(row.get("status", "")).lower() not in {"success", "completed"}
    ]
    if not failed_runs:
        return []

    return [
        {
            "severity": "warning",
            "code": "tracking_runs_not_successful",
            "count": len(failed_runs),
            "examples": [
                {
                    "id": row.get("id"),
                    "source_system": row.get("source_system"),
                    "status": row.get("status"),
                }
                for row in failed_runs[:5]
            ],
            "message": "Tracking contains latest runs that did not finish successfully.",
        }
    ]


def probe_sigpesq_groups() -> dict[str, Any]:
    files = sorted(glob("data/raw/sigpesq/research_group/*.xlsx"))
    if not files:
        return {"origin": "sigpesq_research_group", "files": [], "extracted_counts": {}}
    latest = max(files, key=lambda path: Path(path).stat().st_mtime)
    row_count = len(pd.read_excel(latest))
    return {
        "origin": "sigpesq_research_group",
        "files": [latest],
        "extracted_counts": {"research_groups_rows": row_count},
    }


def probe_sigpesq_projects() -> dict[str, Any]:
    files = sorted(glob("data/raw/sigpesq/research_projects/*.xlsx"))
    if not files:
        return {
            "origin": "sigpesq_research_projects",
            "files": [],
            "extracted_counts": {},
        }
    latest = max(files, key=lambda path: Path(path).stat().st_mtime)
    row_count = len(pd.read_excel(latest))
    return {
        "origin": "sigpesq_research_projects",
        "files": [latest],
        "extracted_counts": {"research_projects_rows": row_count},
    }


def probe_sigpesq_advisorships() -> dict[str, Any]:
    files = sorted(glob("data/raw/sigpesq/advisorships/**/*.xlsx", recursive=True))
    extracted = {}
    total_rows = 0
    for path in files:
        row_count = len(pd.read_excel(path))
        extracted[Path(path).name] = row_count
        total_rows += row_count
    return {
        "origin": "sigpesq_advisorships",
        "files": files,
        "extracted_counts": {
            "advisorship_files": len(files),
            "advisorship_rows_total": total_rows,
            **extracted,
        },
    }


def probe_lattes_projects() -> dict[str, Any]:
    parser = LattesParser()
    files = sorted(glob("data/lattes_json/*.json"))
    projects = 0
    articles = 0
    educations = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        projects += len(parser.parse_research_projects(data))
        projects += len(parser.parse_extension_projects(data))
        projects += len(parser.parse_development_projects(data))
        articles += len(parser.parse_articles(data))
        articles += len(parser.parse_conference_papers(data))
        educations += len(parser.parse_academic_education(data))
    return {
        "origin": "lattes_projects",
        "files": files,
        "extracted_counts": {
            "lattes_files": len(files),
            "projects_total": projects,
            "articles_total": articles,
            "educations_total": educations,
        },
    }


def probe_lattes_advisorships() -> dict[str, Any]:
    parser = LattesParser()
    files = sorted(glob("data/lattes_json/*.json"))
    advisorships = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        advisorships += len(parser.parse_advisorships(data))
    return {
        "origin": "lattes_advisorships",
        "files": files,
        "extracted_counts": {
            "lattes_files": len(files),
            "advisorships_total": advisorships,
        },
    }


def probe_cnpq_sync(campus_name: Optional[str] = None) -> dict[str, Any]:
    with sqlite3.connect("db/horizon.db") as conn:
        conn.row_factory = sqlite3.Row
        if campus_name:
            campus = conn.execute(
                "SELECT id, name FROM organizational_units WHERE lower(name) LIKE lower(?) LIMIT 1",
                (f"%{campus_name}%",),
            ).fetchone()
            if not campus:
                return {
                    "origin": "cnpq_sync",
                    "files": [],
                    "extracted_counts": {
                        "groups_to_sync": 0,
                        "campus_name": campus_name,
                    },
                }
            count = conn.execute(
                """
                SELECT COUNT(*) FROM research_groups
                WHERE campus_id = ?
                  AND cnpq_url IS NOT NULL
                  AND trim(cnpq_url) != ''
                """,
                (campus["id"],),
            ).fetchone()[0]
            return {
                "origin": "cnpq_sync",
                "files": [],
                "extracted_counts": {
                    "groups_to_sync": count,
                    "campus_name": campus["name"],
                },
            }
        count = conn.execute(
            """
            SELECT COUNT(*) FROM research_groups
            WHERE cnpq_url IS NOT NULL
              AND trim(cnpq_url) != ''
            """
        ).fetchone()[0]
    return {
        "origin": "cnpq_sync",
        "files": [],
        "extracted_counts": {
            "groups_to_sync": count,
            "campus_name": campus_name or "all",
        },
    }


class ETLFlowReporter:
    def __init__(
        self,
        *,
        db_path: str = "db/horizon.db",
        output_dir: str = "data/reports",
        run_name: str = "etl_flow_report",
    ):
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.run_name = run_name
        self.started_at = datetime.now().isoformat()
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.steps: list[dict[str, Any]] = []

    def run_step(
        self,
        *,
        step_name: str,
        runner: Callable[[], Any],
        source_probe: Optional[Callable[[], dict[str, Any]]] = None,
    ) -> Any:
        before_tables = _snapshot_tables(self.db_path)
        before_duplicates = _duplicate_summary(self.db_path)
        source_data = (
            source_probe()
            if source_probe
            else {"origin": step_name, "files": [], "extracted_counts": {}}
        )
        started = time.time()
        error = None
        result = None
        tracking_run_id = None

        try:
            if _has_tracking_schema(self.db_path):
                with tracking_recorder.run_context(
                    source_system=source_data.get("origin", step_name),
                    flow_name=step_name,
                ) as tracking_run:
                    tracking_run_id = getattr(tracking_run, "id", None)
                    result = runner()
            else:
                result = runner()
            return result
        except (Exception, SQLAlchemyError) as exc:
            error = str(exc)
            raise
        finally:
            after_tables = _snapshot_tables(self.db_path)
            after_duplicates = _duplicate_summary(self.db_path)
            step_warnings = _step_warnings(
                origin=source_data.get("origin"),
                before_duplicates=before_duplicates,
                after_duplicates=after_duplicates,
            )
            step_warnings.extend(
                _result_warnings(
                    result,
                    default_source=source_data.get("origin") or step_name,
                )
            )
            self.steps.append(
                {
                    "step_name": step_name,
                    "origin": source_data.get("origin"),
                    "source_files": source_data.get("files", []),
                    "extracted_counts": source_data.get("extracted_counts", {}),
                    "duration_seconds": round(time.time() - started, 2),
                    "status": "failed" if error else "success",
                    "error": error,
                    "tracking_run_id": tracking_run_id,
                    "saved_entities": self._table_deltas(before_tables, after_tables),
                    "duplicates_before": before_duplicates,
                    "duplicates_after": after_duplicates,
                    "warnings": step_warnings,
                }
            )

    def _table_deltas(
        self, before: dict[str, int], after: dict[str, int]
    ) -> list[dict[str, Any]]:
        rows = []
        for table in TRACKED_TABLES:
            before_value = before.get(table, 0)
            after_value = after.get(table, 0)
            delta = after_value - before_value
            if delta != 0:
                rows.append(
                    {
                        "entity": table,
                        "before": before_value,
                        "after": after_value,
                        "delta": delta,
                    }
                )
        return rows

    def write(self) -> tuple[Path, Path]:
        final_duplicates = _duplicate_summary(self.db_path)
        tracking_summary = _tracking_summary(self.db_path)
        report = {
            "run_name": self.run_name,
            "run_stamp": self.run_stamp,
            "started_at": self.started_at,
            "finished_at": datetime.now().isoformat(),
            "db_path": self.db_path,
            "steps": self.steps,
            "final_duplicates": final_duplicates,
            "final_tables": _snapshot_tables(self.db_path),
            "tracking_summary": tracking_summary,
            "warnings_by_source": _warnings_by_source(
                db_path=self.db_path,
                steps=self.steps,
                final_duplicates=final_duplicates,
                tracking_summary=tracking_summary,
            ),
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / f"{self.run_name}_{self.run_stamp}.json"
        md_path = self.output_dir / f"{self.run_name}_{self.run_stamp}.md"
        latest_json_path = self.output_dir / f"{self.run_name}.json"
        latest_md_path = self.output_dir / f"{self.run_name}.md"
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        latest_json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        latest_md_path.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        return json_path, md_path

    def _render_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            "# Relatorio de Execucao do ETL",
            "",
            f"Inicio: **{report['started_at']}**",
            f"Fim: **{report['finished_at']}**",
            "",
            "## Etapas",
            "",
        ]

        for step in report["steps"]:
            lines.extend(
                [
                    f"### {step['step_name']}",
                    "",
                    f"- Status: **{step['status']}**",
                    f"- Origem: **{step['origin']}**",
                    f"- Duracao: **{step['duration_seconds']}s**",
                ]
            )
            if step["error"]:
                lines.append(f"- Erro: `{step['error']}`")
            if step.get("tracking_run_id"):
                lines.append(f"- Tracking run id: **{step['tracking_run_id']}**")
            if step["source_files"]:
                lines.append(f"- Arquivos de origem: **{len(step['source_files'])}**")
            if step.get("warnings"):
                lines.append(f"- Warnings: **{len(step['warnings'])}**")
            lines.append("")
            lines.append("#### Quantidade Extraida")
            lines.append("")
            lines.extend(
                [
                    f"- `{key}`: **{value}**"
                    for key, value in step["extracted_counts"].items()
                ]
                or ["- Nenhuma metrica de extracao registrada."]
            )
            lines.append("")
            lines.append("#### Entidades Salvas")
            lines.append("")
            if step["saved_entities"]:
                lines.append("| Entidade | Antes | Depois | Delta |")
                lines.append("| --- | --- | --- | --- |")
                for row in step["saved_entities"]:
                    lines.append(
                        f"| {row['entity']} | {row['before']} | {row['after']} | {row['delta']} |"
                    )
            else:
                lines.append("- Nenhuma entidade teve delta de contagem.")
            lines.append("")

        lines.extend(["## Warnings por Fonte", ""])
        warnings_by_source = report.get("warnings_by_source", {})
        if not warnings_by_source:
            lines.append("- Nenhum warning estruturado registrado.")
        else:
            for source, warnings in warnings_by_source.items():
                lines.extend([f"### {source}", ""])
                lines.append("| Codigo | Severidade | Contagem | Mensagem |")
                lines.append("| --- | --- | --- | --- |")
                for warning in warnings:
                    lines.append(
                        "| {code} | {severity} | {count} | {message} |".format(
                            code=warning.get("code", ""),
                            severity=warning.get("severity", ""),
                            count=warning.get("count", ""),
                            message=warning.get("message", ""),
                        )
                    )
                lines.append("")

        lines.extend(
            [
                "## Estado Final",
                "",
                "| Check | Quantidade |",
                "| --- | --- |",
            ]
        )
        for key, value in report["final_duplicates"].items():
            lines.append(f"| {key} | {value} |")

        tracking_summary = report.get("tracking_summary", {})
        lines.extend(["", "## Tracking Summary", ""])
        if not tracking_summary.get("enabled"):
            lines.append(f"- {tracking_summary.get('note', 'Tracking desabilitado.')}")
        else:
            lines.append("| Tabela | Quantidade |")
            lines.append("| --- | --- |")
            for key, value in tracking_summary.get("totals", {}).items():
                lines.append(f"| {key} | {value} |")
            latest_runs = tracking_summary.get("latest_runs", [])
            if latest_runs:
                lines.extend(
                    [
                        "",
                        "### Ultimos Tracking Runs",
                        "",
                        "| id | source_system | flow_name | status | started_at | finished_at |",
                        "| --- | --- | --- | --- | --- | --- |",
                    ]
                )
                for row in latest_runs:
                    lines.append(
                        f"| {row.get('id')} | {row.get('source_system')} | {row.get('flow_name')} | {row.get('status')} | {row.get('started_at')} | {row.get('finished_at')} |"
                    )

        return "\n".join(lines).rstrip() + "\n"
