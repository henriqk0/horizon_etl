import json
import sqlite3
import zipfile

from src.scripts.verify_team_membership_integrity import (
    count_collision_affected_rows,
    count_duplicate_team_member_rows,
)


def _base_schema(conn):
    conn.executescript("""
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT, description TEXT);
        CREATE TABLE research_groups (id INTEGER PRIMARY KEY);
        CREATE TABLE initiatives (id INTEGER PRIMARY KEY, name TEXT, description TEXT);
        CREATE TABLE initiative_teams (initiative_id INTEGER, team_id INTEGER, PRIMARY KEY (initiative_id, team_id));
        CREATE TABLE persons (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE team_members (
            id INTEGER PRIMARY KEY, team_id INTEGER, person_id INTEGER,
            role_id INTEGER, start_date TEXT, end_date TEXT
        );
        CREATE TABLE entity_change_logs (
            id INTEGER PRIMARY KEY, canonical_entity_type TEXT, canonical_entity_id INTEGER,
            operation TEXT, before_json TEXT, after_json TEXT
        );
        """)


def test_count_duplicate_team_member_rows_reports_zero_when_clean():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 1, 1, 1)"
    )

    assert count_duplicate_team_member_rows(conn) == 0


def test_count_duplicate_team_member_rows_reports_remaining_duplicates():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (2, 1, 1, 1)"
    )

    assert count_duplicate_team_member_rows(conn) == 1


def test_count_collision_affected_rows_reports_zero_when_clean(tmp_path):
    archive_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(
            "research_groups_canonical.json",
            json.dumps(
                [
                    {
                        "id": 9,
                        "name": "G",
                        "members": [{"id": 281, "name": "Real Member"}],
                    }
                ]
            ),
        )
        zf.writestr("initiatives_canonical.json", json.dumps([]))

    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute("INSERT INTO research_groups (id) VALUES (9)")
    conn.execute("INSERT INTO persons (id, name) VALUES (281, 'Real Member')")
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 9, 281, 1)"
    )

    affected_groups, unresolved_rows = count_collision_affected_rows(
        conn, str(archive_path)
    )

    assert affected_groups == 0
    assert unresolved_rows == 0


def test_count_collision_affected_rows_reports_remaining_unresolved_rows(tmp_path):
    archive_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(
            "research_groups_canonical.json",
            json.dumps(
                [
                    {
                        "id": 9,
                        "name": "G",
                        "members": [{"id": 281, "name": "Real Member"}],
                    }
                ]
            ),
        )
        zf.writestr(
            "initiatives_canonical.json",
            json.dumps([{"id": 9, "name": "I", "team": []}]),
        )

    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute("INSERT INTO research_groups (id) VALUES (9)")
    conn.execute("INSERT INTO initiatives (id, name) VALUES (9, 'I')")
    conn.execute("INSERT INTO persons (id, name) VALUES (281, 'Real Member')")
    conn.execute("INSERT INTO persons (id, name) VALUES (999, 'Nobody Knows Them')")
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 9, 281, 1)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (2, 9, 999, 1)"
    )

    affected_groups, unresolved_rows = count_collision_affected_rows(
        conn, str(archive_path)
    )

    assert affected_groups == 1
    assert unresolved_rows == 1
