import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Any, Iterable

from src.adapters.sources.lattes_parser import LattesParser
from src.core.logic.duplicate_auditor import DuplicateAuditor
from src.core.logic.initiative_identity import normalize_text
from src.research_domain_compat import AdvisorshipRole

DB_PATH = "db/horizon.db"
LATTES_DIR = "data/lattes_json"
SIGPESQ_DIR = "data/raw/sigpesq"
OUTPUT_PATH = "data/reports/etl_load_report.json"
ADVISORSHIP_STUDENT_ROLE = AdvisorshipRole.STUDENT.value
ADVISORSHIP_SUPERVISOR_ROLE = AdvisorshipRole.SUPERVISOR.value


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _safe_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _build_people_index(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.identification_id, r.cnpq_url
        FROM persons p
        LEFT JOIN researchers r ON r.id = p.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _resolve_researcher_id(
    people: Iterable[dict[str, Any]], *, lattes_id: str | None, json_name: str | None
) -> int | None:
    canonical_name = normalize_text(json_name)
    for person in people:
        identification_id = str(person.get("identification_id") or "").strip()
        cnpq_url = str(person.get("cnpq_url") or "").strip()
        if lattes_id and (identification_id == lattes_id or lattes_id in cnpq_url):
            return int(person["id"])

    if not canonical_name:
        return None

    for person in people:
        if normalize_text(person.get("name")) == canonical_name:
            return int(person["id"])

    return None


def _project_keys(parser: LattesParser, data: dict[str, Any]) -> set[str]:
    projects = []
    projects.extend(parser.parse_research_projects(data))
    projects.extend(parser.parse_extension_projects(data))
    projects.extend(parser.parse_development_projects(data))
    return {
        normalize_text(project.get("name"))
        for project in projects
        if project.get("name")
    }


def _article_key(parser: LattesParser, article: dict[str, Any]) -> str:
    doi = (article.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return f"title_year:{parser.normalize_title(article.get('title'))}|{article.get('year') or ''}"


def _article_keys(parser: LattesParser, data: dict[str, Any]) -> set[str]:
    articles = []
    articles.extend(parser.parse_articles(data))
    articles.extend(parser.parse_conference_papers(data))
    return {
        _article_key(parser, article) for article in articles if article.get("title")
    }


def _education_key(education: dict[str, Any]) -> str:
    return "|".join(
        [
            normalize_text(education.get("institution")),
            normalize_text(education.get("degree")),
            normalize_text(education.get("course_name")),
            str(education.get("start_year") or ""),
            str(education.get("end_year") or ""),
            normalize_text(education.get("thesis_title")),
        ]
    )


def _education_keys(parser: LattesParser, data: dict[str, Any]) -> set[str]:
    return {
        _education_key(education)
        for education in parser.parse_academic_education(data)
        if education.get("course_name") or education.get("degree")
    }


def _advisorship_key(advisorship: dict[str, Any]) -> str:
    return "|".join(
        [
            normalize_text(advisorship.get("title")),
            normalize_text(advisorship.get("student_name")),
            normalize_text(advisorship.get("type_name")),
            str(advisorship.get("start_year") or ""),
            str(advisorship.get("end_year") or ""),
        ]
    )


def _advisorship_keys(parser: LattesParser, data: dict[str, Any]) -> set[str]:
    return {
        _advisorship_key(advisorship)
        for advisorship in parser.parse_advisorships(data)
        if advisorship.get("title")
    }


def _db_article_keys(conn: sqlite3.Connection, researcher_id: int) -> set[str]:
    rows = conn.execute(
        """
        SELECT a.title, a.year, a.doi
        FROM articles a
        JOIN article_authors aa ON aa.article_id = a.id
        WHERE aa.researcher_id = ?
        """,
        (researcher_id,),
    ).fetchall()
    parser = LattesParser()
    return {
        (
            f"doi:{row['doi'].strip().lower()}"
            if (row["doi"] or "").strip()
            else f"title_year:{parser.normalize_title(row['title'])}|{row['year'] or ''}"
        )
        for row in rows
    }


def _db_education_keys(conn: sqlite3.Connection, researcher_id: int) -> set[str]:
    rows = conn.execute(
        """
        SELECT ae.start_year, ae.end_year, ae.thesis_title, ae.title, et.name AS degree, o.name AS institution
        FROM academic_educations ae
        LEFT JOIN education_types et ON et.id = ae.education_type_id
        LEFT JOIN organizations o ON o.id = ae.institution_id
        WHERE ae.researcher_id = ?
        """,
        (researcher_id,),
    ).fetchall()
    return {
        "|".join(
            [
                normalize_text(row["institution"]),
                normalize_text(row["degree"]),
                normalize_text(row["title"]),
                str(row["start_year"] or ""),
                str(row["end_year"] or ""),
                normalize_text(row["thesis_title"]),
            ]
        )
        for row in rows
    }


def _db_advisorship_keys(conn: sqlite3.Connection, researcher_id: int) -> set[str]:
    if _table_exists(conn, "advisorship_members"):
        rows = conn.execute(
            """
            SELECT i.name AS title, p.name AS student_name, a.type, i.start_date, i.end_date
            FROM advisorships a
            JOIN initiatives i ON i.id = a.id
            LEFT JOIN (
                SELECT advisorship_id, MIN(person_id) AS student_id
                FROM advisorship_members
                WHERE role_name = ?
                GROUP BY advisorship_id
            ) am_std ON am_std.advisorship_id = a.id
            LEFT JOIN persons p ON p.id = am_std.student_id
            JOIN (
                SELECT advisorship_id, MIN(person_id) AS supervisor_id
                FROM advisorship_members
                WHERE role_name = ?
                GROUP BY advisorship_id
            ) am_sup ON am_sup.advisorship_id = a.id
            WHERE am_sup.supervisor_id = ?
            """,
            (
                ADVISORSHIP_STUDENT_ROLE,
                ADVISORSHIP_SUPERVISOR_ROLE,
                researcher_id,
            ),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT i.name AS title, p.name AS student_name, a.type, i.start_date, i.end_date
            FROM advisorships a
            JOIN initiatives i ON i.id = a.id
            LEFT JOIN persons p ON p.id = a.student_id
            WHERE a.supervisor_id = ?
            """,
            (researcher_id,),
        ).fetchall()
    return {
        "|".join(
            [
                normalize_text(row["title"]),
                normalize_text(row["student_name"]),
                normalize_text(row["type"]),
                _year_from_date(row["start_date"]),
                _year_from_date(row["end_date"]),
            ]
        )
        for row in rows
    }


def _db_project_keys(conn: sqlite3.Connection, researcher_id: int) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT i.name
        FROM initiatives i
        LEFT JOIN initiative_types itype ON itype.id = i.initiative_type_id
        LEFT JOIN initiative_teams it ON it.initiative_id = i.id
        LEFT JOIN team_members tm ON tm.team_id = it.team_id
        LEFT JOIN initiative_persons ip ON ip.initiative_id = i.id
        WHERE COALESCE(lower(itype.name), '') != 'advisorship'
          AND (tm.person_id = ? OR ip.person_id = ?)
        """,
        (researcher_id, researcher_id),
    ).fetchall()
    return {normalize_text(row["name"]) for row in rows if row["name"]}


def _year_from_date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:4] if len(text) >= 4 else text


def _top_examples(values: set[str], limit: int = 5) -> list[str]:
    return sorted(value for value in values if value)[:limit]


def _reconcile_entity(extracted: set[str], persisted: set[str]) -> dict[str, Any]:
    missing = extracted - persisted
    extra = persisted - extracted
    return {
        "extracted_unique": len(extracted),
        "persisted_unique": len(persisted),
        "matched": len(extracted & persisted),
        "missing_in_db": len(missing),
        "extra_in_db": len(extra),
        "missing_examples": _top_examples(missing),
        "extra_examples": _top_examples(extra),
    }


def _lattes_reconciliation(conn: sqlite3.Connection) -> dict[str, Any]:
    parser = LattesParser()
    files = sorted(glob(str(Path(LATTES_DIR) / "*.json")))
    people = _build_people_index(conn)

    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    files_with_delta = []
    unresolved_files = []

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        filename = Path(file_path).name
        lattes_id = filename.replace(".json", "").split("_")[-1]
        json_name = (
            data.get("nome")
            or data.get("name")
            or data.get("informacoes_pessoais", {}).get("nome_completo")
        )
        researcher_id = _resolve_researcher_id(
            people, lattes_id=lattes_id, json_name=json_name
        )

        extracted = {
            "projects": _project_keys(parser, data),
            "articles": _article_keys(parser, data),
            "educations": _education_keys(parser, data),
            "advisorships": _advisorship_keys(parser, data),
        }

        if not researcher_id:
            unresolved_files.append(
                {
                    "file": filename,
                    "json_name": json_name,
                    "lattes_id": lattes_id,
                    "extracted": {key: len(value) for key, value in extracted.items()},
                }
            )
            continue

        persisted = {
            "projects": _db_project_keys(conn, researcher_id),
            "articles": _db_article_keys(conn, researcher_id),
            "educations": _db_education_keys(conn, researcher_id),
            "advisorships": _db_advisorship_keys(conn, researcher_id),
        }

        per_file = {
            "file": filename,
            "researcher_id": researcher_id,
            "json_name": json_name,
        }
        has_delta = False
        for entity in ("projects", "articles", "educations", "advisorships"):
            result = _reconcile_entity(extracted[entity], persisted[entity])
            per_file[entity] = result
            for key in (
                "extracted_unique",
                "persisted_unique",
                "matched",
                "missing_in_db",
                "extra_in_db",
            ):
                totals[entity][key] += result[key]
            if result["missing_in_db"] or result["extra_in_db"]:
                has_delta = True

        if has_delta:
            files_with_delta.append(per_file)

    return {
        "lattes_files_total": len(files),
        "resolved_files": len(files) - len(unresolved_files),
        "unresolved_files": unresolved_files,
        "totals": totals,
        "files_with_delta": files_with_delta,
        "limitations": [
            "Projects and advisorships are reconciled by normalized names/keys and researcher ownership because the current SQLite initiatives table does not persist source_identity metadata.",
            "extra_in_db can include records from SigPesq/CNPq or older loads that belong to the same researcher.",
        ],
    }


def _db_inventory(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "persons",
        "researchers",
        "person_emails",
        "organizations",
        "organizational_units",
        "roles",
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
    return {table: _safe_count(conn, table) for table in tables}


def _health_checks(conn: sqlite3.Connection) -> dict[str, int]:
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    if _table_exists(conn, "advisorship_members"):
        advisorships_without_supervisor = count(
            """
            SELECT COUNT(*)
            FROM advisorships a
            WHERE NOT EXISTS (
                SELECT 1
                FROM advisorship_members am
                WHERE am.advisorship_id = a.id
                  AND am.role_name = 'Supervisor'
            )
            """
        )
        advisorships_without_student = count(
            """
            SELECT COUNT(*)
            FROM advisorships a
            WHERE NOT EXISTS (
                SELECT 1
                FROM advisorship_members am
                WHERE am.advisorship_id = a.id
                  AND am.role_name = 'Student'
            )
            """
        )
    else:
        advisorships_without_supervisor = count(
            """
            SELECT COUNT(*)
            FROM advisorships
            WHERE supervisor_id IS NULL
            """
        )
        advisorships_without_student = count(
            """
            SELECT COUNT(*)
            FROM advisorships
            WHERE student_id IS NULL
            """
        )

    return {
        "articles_duplicate_doi": count(
            """
            SELECT COUNT(*) FROM (
                SELECT lower(doi) FROM articles
                WHERE doi IS NOT NULL AND trim(doi) != ''
                GROUP BY lower(doi)
                HAVING COUNT(*) > 1
            )
            """
        ),
        "articles_duplicate_title_year": count(
            """
            SELECT COUNT(*) FROM (
                SELECT lower(title), year FROM articles
                GROUP BY lower(title), year
                HAVING COUNT(*) > 1
            )
            """
        ),
        "advisorships_without_supervisor": advisorships_without_supervisor,
        "advisorships_without_student": advisorships_without_student,
        "initiatives_without_team": count(
            """
            SELECT COUNT(*) FROM initiatives i
            LEFT JOIN initiative_teams it ON it.initiative_id = i.id
            WHERE it.initiative_id IS NULL
            """
        ),
        "research_groups_without_cnpq_url": count(
            """
            SELECT COUNT(*) FROM research_groups
            WHERE cnpq_url IS NULL OR trim(cnpq_url) = ''
            """
        ),
        "researchers_without_resume": count(
            """
            SELECT COUNT(*) FROM researchers
            WHERE resume IS NULL OR trim(resume) = ''
            """
        ),
        "researchers_without_cnpq_url": count(
            """
            SELECT COUNT(*) FROM researchers
            WHERE cnpq_url IS NULL OR trim(cnpq_url) = ''
            """
        ),
    }


def _source_inventory() -> dict[str, Any]:
    lattes_files = sorted(glob(str(Path(LATTES_DIR) / "*.json")))
    sigpesq_files = sorted(glob(str(Path(SIGPESQ_DIR) / "**" / "*.*"), recursive=True))
    return {
        "lattes_json_files": len(lattes_files),
        "sigpesq_source_files": len(
            [path for path in sigpesq_files if Path(path).is_file()]
        ),
        "lattes_examples": [Path(path).name for path in lattes_files[:5]],
        "sigpesq_examples": [str(Path(path)) for path in sigpesq_files[:5]],
    }


def generate_report(db_path: str = DB_PATH) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        duplicate_report = DuplicateAuditor(db_path).run()
        return {
            "generated_at": datetime.now().isoformat(),
            "db_path": db_path,
            "source_inventory": _source_inventory(),
            "db_inventory": _db_inventory(conn),
            "duplicate_summary": {
                key: len(value) for key, value in duplicate_report.items()
            },
            "health_checks": _health_checks(conn),
            "lattes_reconciliation": _lattes_reconciliation(conn),
        }


def main() -> None:
    report = generate_report()
    output_path = Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
