import json
import sqlite3
import zipfile
from pathlib import Path

from src.core.logic.backup_db_provisioner import BackupDatabaseProvisioner


def _write_minimal_archive(path: Path) -> Path:
    """A minimal archive reproducing the confirmed real-world collision:
    research group #9 and initiative #9 share an id, with distinct real
    member sets."""
    archive_path = path / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(
            "research_groups_canonical.json",
            json.dumps(
                [
                    {
                        "id": 9,
                        "name": "Aquicultura e Ambiencia Animal",
                        "campus": {"id": 3},
                        "members": [
                            {
                                "id": 281,
                                "name": "Real Group Member",
                                "role": "Pesquisador",
                            }
                        ],
                    }
                ]
            ),
        )
        zf.writestr(
            "initiatives_canonical.json",
            json.dumps(
                [
                    {
                        "id": 9,
                        "name": "ConectaFAPES",
                        "status": "Active",
                        "team": [
                            {
                                "person_id": 456,
                                "person_name": "Real Initiative Member",
                                "roles": ["Researcher"],
                            }
                        ],
                    }
                ]
            ),
        )
    return archive_path


def test_colliding_group_and_initiative_get_disjoint_team_ids(tmp_path):
    archive_path = _write_minimal_archive(tmp_path)
    db_path = tmp_path / "provisioned.db"

    provisioner = BackupDatabaseProvisioner()
    provisioner._build_database_from_archive(db_path, archive_path)

    conn = sqlite3.connect(str(db_path))
    group_team_id = conn.execute(
        "SELECT id FROM research_groups WHERE id = 9"
    ).fetchone()[0]
    assert group_team_id == 9  # unchanged, per FR-003

    initiative_team_id = conn.execute(
        "SELECT team_id FROM initiative_teams WHERE initiative_id = 9 "
        "AND team_id NOT IN (SELECT id FROM research_groups)"
    ).fetchone()[0]
    assert initiative_team_id != 9  # disjoint from the colliding group id

    group_members = {
        row[0]
        for row in conn.execute(
            "SELECT person_id FROM team_members WHERE team_id = 9"
        ).fetchall()
    }
    initiative_members = {
        row[0]
        for row in conn.execute(
            "SELECT person_id FROM team_members WHERE team_id = ?",
            (initiative_team_id,),
        ).fetchall()
    }
    assert group_members == {281}
    assert initiative_members == {456}


def test_single_build_never_inserts_duplicate_team_members(tmp_path):
    """Regression guard for the real root cause of the 23.5%-duplicate-rows
    bug: section 11b derives the same initiative-team relationship from two
    different views of the source archive (the initiative's own team list,
    and each researcher's own initiatives list), inserting it twice. Without
    a uniqueness constraint, INSERT OR IGNORE can't tell they're the same
    relationship. This must never happen even from a single archive build."""
    # A person listed on BOTH views for the same initiative -- the exact
    # shape that produced duplicates in the real archive.
    archive_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(
            "research_groups_canonical.json",
            json.dumps([]),
        )
        zf.writestr(
            "initiatives_canonical.json",
            json.dumps(
                [
                    {
                        "id": 500,
                        "name": "Some Project",
                        "status": "Active",
                        "team": [
                            {
                                "person_id": 456,
                                "person_name": "Paulo",
                                "roles": ["Researcher"],
                            }
                        ],
                    }
                ]
            ),
        )
        zf.writestr(
            "researchers_canonical.json",
            json.dumps(
                [
                    {
                        "id": 456,
                        "name": "Paulo",
                        "initiatives": [{"id": 500, "role": "Researcher"}],
                    }
                ]
            ),
        )
    db_path = tmp_path / "dedup_check.db"

    provisioner = BackupDatabaseProvisioner()
    provisioner._build_database_from_archive(db_path, archive_path)

    conn = sqlite3.connect(str(db_path))
    dup_groups = conn.execute("""
        SELECT team_id, person_id, role_id, COUNT(*) c
        FROM team_members
        GROUP BY team_id, person_id, role_id
        HAVING c > 1
        """).fetchall()
    assert dup_groups == []


def test_reprovisioning_does_not_grow_team_members(tmp_path):
    archive_path = _write_minimal_archive(tmp_path)
    db_path = tmp_path / "provisioned.db"

    provisioner = BackupDatabaseProvisioner()
    provisioner._build_database_from_archive(db_path, archive_path)
    conn = sqlite3.connect(str(db_path))
    first_count = conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0]
    first_initiative_team_id = conn.execute(
        "SELECT team_id FROM initiative_teams WHERE initiative_id = 9 "
        "AND team_id NOT IN (SELECT id FROM research_groups)"
    ).fetchone()[0]
    conn.close()

    # Re-provision from the same archive into the same path.
    provisioner._build_database_from_archive(db_path, archive_path)
    conn = sqlite3.connect(str(db_path))
    second_count = conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0]
    second_initiative_team_id = conn.execute(
        "SELECT team_id FROM initiative_teams WHERE initiative_id = 9 "
        "AND team_id NOT IN (SELECT id FROM research_groups)"
    ).fetchone()[0]

    assert second_count == first_count
    assert second_initiative_team_id == first_initiative_team_id
