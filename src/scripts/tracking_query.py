import argparse
import json
import sqlite3

DB_PATH = "db/horizon.db"


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query tracking data for audit purposes."
    )
    parser.add_argument("--db-path", default=DB_PATH)
    parser.add_argument("--entity-type")
    parser.add_argument("--entity-id", type=int)
    parser.add_argument("--source-system")
    parser.add_argument("--attribute")
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        required = [
            "ingestion_runs",
            "source_records",
            "entity_matches",
            "attribute_assertions",
            "entity_change_logs",
        ]
        if not all(_has_table(conn, table) for table in required):
            print(
                json.dumps(
                    {
                        "note": "Tracking tables not found in current database. Run reset/full-refresh after tracking schema migration."
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

        filters = []
        params = []
        if args.entity_type:
            filters.append("ecl.canonical_entity_type = ?")
            params.append(args.entity_type)
        if args.entity_id is not None:
            filters.append("ecl.canonical_entity_id = ?")
            params.append(args.entity_id)
        if args.source_system:
            filters.append("ir.source_system = ?")
            params.append(args.source_system)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        changes = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    ecl.id,
                    ecl.canonical_entity_type,
                    ecl.canonical_entity_id,
                    ecl.operation,
                    ecl.changed_fields_json,
                    ecl.reason,
                    ecl.changed_at,
                    ir.id AS ingestion_run_id,
                    ir.source_system,
                    ir.flow_name
                FROM entity_change_logs ecl
                JOIN ingestion_runs ir ON ir.id = ecl.ingestion_run_id
                {where_clause}
                ORDER BY ecl.id DESC
                LIMIT ?
                """,
                (*params, args.limit),
            ).fetchall()
        ]

        assertion_filters = []
        assertion_params = []
        if args.entity_type:
            assertion_filters.append("aa.canonical_entity_type = ?")
            assertion_params.append(args.entity_type)
        if args.entity_id is not None:
            assertion_filters.append("aa.canonical_entity_id = ?")
            assertion_params.append(args.entity_id)
        if args.attribute:
            assertion_filters.append("aa.attribute_name = ?")
            assertion_params.append(args.attribute)
        if args.source_system:
            assertion_filters.append("sr.source_system = ?")
            assertion_params.append(args.source_system)

        assertion_where = (
            f"WHERE {' AND '.join(assertion_filters)}" if assertion_filters else ""
        )

        assertions = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    aa.id,
                    aa.canonical_entity_type,
                    aa.canonical_entity_id,
                    aa.attribute_name,
                    aa.value_json,
                    aa.selection_reason,
                    aa.asserted_at,
                    sr.source_system,
                    sr.source_entity_type,
                    sr.source_file
                FROM attribute_assertions aa
                JOIN source_records sr ON sr.id = aa.source_record_id
                {assertion_where}
                ORDER BY aa.id DESC
                LIMIT ?
                """,
                (*assertion_params, args.limit),
            ).fetchall()
        ]

        matches = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    em.id,
                    em.canonical_entity_type,
                    em.canonical_entity_id,
                    em.match_strategy,
                    em.match_confidence,
                    em.matched_at,
                    sr.source_system,
                    sr.source_entity_type,
                    sr.source_record_id,
                    sr.source_file
                FROM entity_matches em
                JOIN source_records sr ON sr.id = em.source_record_id
                WHERE (? IS NULL OR em.canonical_entity_type = ?)
                  AND (? IS NULL OR em.canonical_entity_id = ?)
                  AND (? IS NULL OR sr.source_system = ?)
                ORDER BY em.id DESC
                LIMIT ?
                """,
                (
                    args.entity_type,
                    args.entity_type,
                    args.entity_id,
                    args.entity_id,
                    args.source_system,
                    args.source_system,
                    args.limit,
                ),
            ).fetchall()
        ]

    print(
        json.dumps(
            {
                "filters": {
                    "entity_type": args.entity_type,
                    "entity_id": args.entity_id,
                    "source_system": args.source_system,
                    "attribute": args.attribute,
                    "limit": args.limit,
                },
                "changes": changes,
                "assertions": assertions,
                "matches": matches,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
