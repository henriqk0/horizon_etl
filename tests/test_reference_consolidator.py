import sqlite3
from pathlib import Path

from src.core.logic.reference_consolidator import ReferenceConsolidator


def test_consolidate_knowledge_areas_and_teams(tmp_path: Path):
    db_path = tmp_path / "refs.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE knowledge_areas (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE group_knowledge_areas (group_id INTEGER NOT NULL, area_id INTEGER NOT NULL, PRIMARY KEY (group_id, area_id));
        CREATE TABLE initiative_knowledge_areas (initiative_id INTEGER NOT NULL, area_id INTEGER NOT NULL, PRIMARY KEY (initiative_id, area_id));
        CREATE TABLE researcher_knowledge_areas (researcher_id INTEGER NOT NULL, area_id INTEGER NOT NULL, PRIMARY KEY (researcher_id, area_id));
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, short_name TEXT, organization_id INTEGER);
        CREATE TABLE team_members (id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER NOT NULL, team_id INTEGER NOT NULL, role_id INTEGER, start_date DATETIME, end_date DATETIME);
        CREATE TABLE initiative_teams (initiative_id INTEGER NOT NULL, team_id INTEGER NOT NULL, PRIMARY KEY (initiative_id, team_id));
        CREATE TABLE research_groups (id INTEGER PRIMARY KEY, campus_id INTEGER, cnpq_url TEXT, site TEXT, start_date DATETIME);
        """
    )
    conn.execute("INSERT INTO knowledge_areas (id, name) VALUES (1, 'Física')")
    conn.execute("INSERT INTO knowledge_areas (id, name) VALUES (2, 'Fisica')")
    conn.execute("INSERT INTO group_knowledge_areas (group_id, area_id) VALUES (10, 2)")
    conn.execute(
        "INSERT INTO initiative_knowledge_areas (initiative_id, area_id) VALUES (20, 2)"
    )
    conn.execute(
        "INSERT INTO researcher_knowledge_areas (researcher_id, area_id) VALUES (30, 2)"
    )

    conn.execute(
        "INSERT INTO teams (id, name, description) VALUES (100, 'Conecta FAPES', 'rich')"
    )
    conn.execute(
        "INSERT INTO teams (id, name, description) VALUES (200, 'Conecta Fapes', NULL)"
    )
    conn.execute(
        "INSERT INTO initiative_teams (initiative_id, team_id) VALUES (50, 200)"
    )
    conn.execute(
        "INSERT INTO team_members (person_id, team_id, role_id) VALUES (99, 200, 2)"
    )
    conn.commit()
    conn.close()

    consolidator = ReferenceConsolidator(str(db_path))
    ka_stats = consolidator.consolidate_knowledge_areas()
    team_stats = consolidator.consolidate_teams()

    check = sqlite3.connect(db_path)
    cur = check.cursor()
    assert ka_stats.merged == 1
    assert (
        cur.execute("SELECT COUNT(*) FROM knowledge_areas WHERE id = 2").fetchone()[0]
        == 0
    )
    assert (
        cur.execute(
            "SELECT area_id FROM group_knowledge_areas WHERE group_id = 10"
        ).fetchone()[0]
        == 1
    )
    assert (
        cur.execute(
            "SELECT area_id FROM initiative_knowledge_areas WHERE initiative_id = 20"
        ).fetchone()[0]
        == 1
    )
    assert (
        cur.execute(
            "SELECT area_id FROM researcher_knowledge_areas WHERE researcher_id = 30"
        ).fetchone()[0]
        == 1
    )

    assert team_stats.merged == 1
    remaining_team_ids = [
        row[0] for row in cur.execute("SELECT id FROM teams ORDER BY id").fetchall()
    ]
    assert len(remaining_team_ids) == 1
    survivor_id = remaining_team_ids[0]
    assert (
        cur.execute(
            "SELECT team_id FROM initiative_teams WHERE initiative_id = 50"
        ).fetchone()[0]
        == survivor_id
    )
    assert (
        cur.execute("SELECT team_id FROM team_members WHERE person_id = 99").fetchone()[
            0
        ]
        == survivor_id
    )
