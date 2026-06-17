import json
import sqlite3
from pathlib import Path

DB_PATH = "db/horizon.db"
JSON_OUTPUT = "data/reports/tracking_audit_report.json"
MD_OUTPUT = "data/reports/tracking_audit_report.md"


def _fetch_all(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def build_report(db_path: str = DB_PATH) -> dict:
    with sqlite3.connect(db_path) as conn:
        required_tables = [
            "ingestion_runs",
            "source_records",
            "entity_matches",
            "attribute_assertions",
            "entity_change_logs",
        ]
        if not all(_has_table(conn, table) for table in required_tables):
            return {
                "ingestion_runs": [],
                "source_records_by_source": [],
                "entity_matches_by_target": [],
                "selected_assertions_by_attribute": [],
                "changes_by_operation": [],
                "latest_runs": [],
                "note": "Tracking tables not found in current database. Run reset/full-refresh after tracking schema migration.",
            }
        summary = {
            "ingestion_runs": _fetch_all(
                conn,
                """
                SELECT source_system, flow_name, status, COUNT(*) AS total_runs
                FROM ingestion_runs
                GROUP BY source_system, flow_name, status
                ORDER BY total_runs DESC, source_system, flow_name
                """,
            ),
            "source_records_by_source": _fetch_all(
                conn,
                """
                SELECT source_system, source_entity_type, COUNT(*) AS total_records
                FROM source_records
                GROUP BY source_system, source_entity_type
                ORDER BY total_records DESC, source_system, source_entity_type
                """,
            ),
            "entity_matches_by_target": _fetch_all(
                conn,
                """
                SELECT canonical_entity_type, match_strategy, COUNT(*) AS total_matches
                FROM entity_matches
                GROUP BY canonical_entity_type, match_strategy
                ORDER BY total_matches DESC, canonical_entity_type, match_strategy
                """,
            ),
            "selected_assertions_by_attribute": _fetch_all(
                conn,
                """
                SELECT canonical_entity_type, attribute_name, COUNT(*) AS total_selected
                FROM attribute_assertions
                WHERE is_selected = 1
                GROUP BY canonical_entity_type, attribute_name
                ORDER BY total_selected DESC, canonical_entity_type, attribute_name
                """,
            ),
            "changes_by_operation": _fetch_all(
                conn,
                """
                SELECT canonical_entity_type, operation, COUNT(*) AS total_changes
                FROM entity_change_logs
                GROUP BY canonical_entity_type, operation
                ORDER BY total_changes DESC, canonical_entity_type, operation
                """,
            ),
            "latest_runs": _fetch_all(
                conn,
                """
                SELECT id, source_system, flow_name, status, started_at, finished_at, notes
                FROM ingestion_runs
                ORDER BY id DESC
                LIMIT 20
                """,
            ),
        }
    return summary


def _table(rows: list[dict]) -> str:
    if not rows:
        return "- Sem dados."
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(row.get(header, "")) for header in headers) + " |"
        )
    return "\n".join(lines)


def render_markdown(report: dict) -> str:
    sections = ["# Relatorio de Auditoria do Tracking", ""]
    if report.get("note"):
        sections.extend([f"- {report['note']}", ""])
    mapping = [
        ("Execucoes por Fonte", "ingestion_runs"),
        ("Registros Brutos por Fonte", "source_records_by_source"),
        ("Matches por Entidade Canonica", "entity_matches_by_target"),
        ("Atributos Selecionados", "selected_assertions_by_attribute"),
        ("Mudancas por Operacao", "changes_by_operation"),
        ("Ultimas Execucoes", "latest_runs"),
    ]
    for title, key in mapping:
        sections.extend([f"## {title}", "", _table(report[key]), ""])
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    report = build_report()
    Path(JSON_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    Path(JSON_OUTPUT).write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown = render_markdown(report)
    Path(MD_OUTPUT).write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
