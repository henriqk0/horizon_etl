import sqlite3
from pathlib import Path

from src.core.logic.duplicate_auditor import DuplicateAuditor


def test_duplicate_auditor_reports_canonical_duplicates(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE persons (id INTEGER PRIMARY KEY, name TEXT, identification_id TEXT);
        CREATE TABLE person_emails (id INTEGER PRIMARY KEY, person_id INTEGER, email TEXT);
        CREATE TABLE organizations (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE organizational_units (id INTEGER PRIMARY KEY, name TEXT, organization_id INTEGER);
        CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE initiative_types (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE knowledge_areas (id INTEGER PRIMARY KEY, name TEXT);
        """
    )
    conn.execute("INSERT INTO persons (id, name) VALUES (1, 'Gustavo Maia De Almeida')")
    conn.execute("INSERT INTO persons (id, name) VALUES (2, 'Gustavo Maia de Almeida')")
    conn.commit()
    conn.close()

    report = DuplicateAuditor(str(db_path)).run()

    assert len(report["persons_by_canonical_name"]) == 1
    assert (
        report["persons_by_canonical_name"][0]["canonical"] == "gustavo maia de almeida"
    )
