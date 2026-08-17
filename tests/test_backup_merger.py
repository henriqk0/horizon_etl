import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest

from src.core.logic.backup_db_provisioner import BackupDatabaseProvisioner
from src.core.logic.backup_merger import BackupDatabaseMerger


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backup_db = tmp_path / "horizon_backup.db"
        active_db = tmp_path / "horizon_active.db"
        zip_path = tmp_path / "novo_backup.zip"

        # Create dummy zip archive with canonical json files
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(
                "organizations_canonical.json",
                json.dumps([{"id": 1, "name": "IFES", "short_name": "IFES"}]),
            )
            zf.writestr(
                "campuses_canonical.json",
                json.dumps([{"id": 1, "name": "Serra", "organization_id": 1}]),
            )
            zf.writestr(
                "researchers_canonical.json",
                json.dumps(
                    [
                        {"id": 1, "name": "Researcher A", "lattes_id": "1111"},
                        {"id": 2, "name": "Researcher B", "lattes_id": "2222"},
                    ]
                ),
            )
            zf.writestr(
                "initiatives_canonical.json",
                json.dumps(
                    [
                        {"id": 10, "name": "Project 1", "description": "Desc 1"},
                        {"id": 20, "name": "Project 2", "description": "Desc 2"},
                    ]
                ),
            )
            zf.writestr(
                "articles_canonical.json",
                json.dumps(
                    [
                        {
                            "id": 100,
                            "title": "Article 1",
                            "doi": "doi/1",
                            "year": 2024,
                            "type": "Journal",
                        }
                    ]
                ),
            )

        yield {
            "tmp_path": tmp_path,
            "backup_db": backup_db,
            "active_db": active_db,
            "zip_path": zip_path,
        }


def test_backup_database_provisioning(temp_env):
    provisioner = BackupDatabaseProvisioner()
    db_path = provisioner.ensure_backup_database(
        backup_db_path=temp_env["backup_db"],
        source_archive=temp_env["zip_path"],
        force_rebuild=True,
    )
    assert db_path.is_file()

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM persons")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM initiatives")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM articles")
        assert cur.fetchone()[0] == 1


def test_backup_merger_into_empty_active_db(temp_env):
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env["backup_db"],
        source_archive=temp_env["zip_path"],
        force_rebuild=True,
    )

    merger = BackupDatabaseMerger(provisioner=provisioner)
    result = merger.merge(temp_env["active_db"], temp_env["backup_db"])
    assert result["status"] in ["success", "cloned_from_backup"]

    with sqlite3.connect(str(temp_env["active_db"])) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM persons")
        assert cur.fetchone()[0] == 2


def test_backup_merger_with_partial_active_db(temp_env):
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env["backup_db"],
        source_archive=temp_env["zip_path"],
        force_rebuild=True,
    )

    # Initialize active DB with only 1 researcher
    with sqlite3.connect(str(temp_env["active_db"])) as conn:
        with sqlite3.connect(str(temp_env["backup_db"])) as bconn:
            cur = bconn.cursor()
            cur.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
            )
            schema_sql = "\n".join(row[0] + ";" for row in cur.fetchall())
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT INTO persons (id, name, identification_id) VALUES (1, 'Researcher A Live', '1111')"
        )
        conn.commit()

    merger = BackupDatabaseMerger(provisioner=provisioner)
    result = merger.merge(temp_env["active_db"], temp_env["backup_db"])
    assert result["status"] == "success"

    with sqlite3.connect(str(temp_env["active_db"])) as conn:
        cur = conn.cursor()
        # Should now have both researcher 1 and researcher 2
        cur.execute("SELECT count(*) FROM persons")
        assert cur.fetchone()[0] == 2
        # Should have both projects 10 and 20
        cur.execute("SELECT count(*) FROM initiatives")
        assert cur.fetchone()[0] == 2


@pytest.fixture
def temp_env_with_knowledge_areas():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backup_db = tmp_path / "horizon_backup.db"
        active_db = tmp_path / "horizon_active.db"
        zip_path = tmp_path / "novo_backup.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(
                "organizations_canonical.json",
                json.dumps([{"id": 1, "name": "IFES", "short_name": "IFES"}]),
            )
            zf.writestr(
                "campuses_canonical.json",
                json.dumps([{"id": 1, "name": "Serra", "organization_id": 1}]),
            )
            zf.writestr(
                "knowledge_areas_canonical.json",
                json.dumps(
                    [
                        {"id": 100, "name": "Microrrede"},
                        {"id": 101, "name": "Metodologias Ágeis"},
                    ]
                ),
            )
            zf.writestr(
                "researchers_canonical.json",
                json.dumps(
                    [
                        {
                            "id": 1,
                            "name": "Researcher A",
                            "lattes_id": "1111",
                            "knowledge_areas": [{"id": 100, "name": "Microrrede"}],
                        },
                        {"id": 2, "name": "Researcher B", "lattes_id": "2222"},
                    ]
                ),
            )
            zf.writestr(
                "research_groups_canonical.json",
                json.dumps(
                    [
                        {
                            "id": 1,
                            "name": "Group A",
                            "campus_id": 1,
                            "knowledge_areas": [
                                {"id": 101, "name": "Metodologias Ágeis"}
                            ],
                        },
                    ]
                ),
            )
            zf.writestr(
                "initiatives_canonical.json",
                json.dumps(
                    [
                        {
                            "id": 10,
                            "name": "Project 1",
                            "description": "Desc 1",
                            "knowledge_areas": [
                                {"id": 100, "name": "Microrrede"},
                                {"id": 999, "name": "Unknown Area"},
                            ],
                        },
                        {"id": 20, "name": "Project 2", "description": "Desc 2"},
                    ]
                ),
            )

        yield {
            "tmp_path": tmp_path,
            "backup_db": backup_db,
            "active_db": active_db,
            "zip_path": zip_path,
        }


def test_backup_database_provisioning_populates_knowledge_area_links(
    temp_env_with_knowledge_areas,
):
    provisioner = BackupDatabaseProvisioner()
    db_path = provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT researcher_id, area_id FROM researcher_knowledge_areas")
        assert cur.fetchall() == [(1, 100)]

        cur.execute("SELECT group_id, area_id FROM group_knowledge_areas")
        assert cur.fetchall() == [(1, 101)]

        # id 999 does not exist in knowledge_areas_canonical.json and must be skipped
        cur.execute("SELECT initiative_id, area_id FROM initiative_knowledge_areas")
        assert cur.fetchall() == [(10, 100)]


def test_knowledge_area_link_skips_unknown_area_id(temp_env_with_knowledge_areas):
    provisioner = BackupDatabaseProvisioner()
    db_path = provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM initiative_knowledge_areas WHERE area_id = 999"
        )
        assert cur.fetchone()[0] == 0
        # The valid link for the same initiative must still be present
        cur.execute(
            "SELECT count(*) FROM initiative_knowledge_areas WHERE initiative_id = 10 AND area_id = 100"
        )
        assert cur.fetchone()[0] == 1


def test_backup_merger_propagates_knowledge_area_links(temp_env_with_knowledge_areas):
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    merger = BackupDatabaseMerger(provisioner=provisioner)
    result = merger.merge(
        temp_env_with_knowledge_areas["active_db"],
        temp_env_with_knowledge_areas["backup_db"],
    )
    assert result["status"] in ["success", "cloned_from_backup"]

    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM researcher_knowledge_areas")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM group_knowledge_areas")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM initiative_knowledge_areas")
        assert cur.fetchone()[0] == 1


def test_knowledge_area_links_are_idempotent_across_repeated_runs(
    temp_env_with_knowledge_areas,
):
    """SC-005: junction table counts must not regress to 0 (or grow unbounded)
    across repeated provision+merge cycles, e.g. consecutive weekly runs."""
    provisioner = BackupDatabaseProvisioner()

    def counts(db_path):
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            result = {}
            for t in (
                "researcher_knowledge_areas",
                "group_knowledge_areas",
                "initiative_knowledge_areas",
            ):
                cur.execute(f"SELECT count(*) FROM {t}")
                result[t] = cur.fetchone()[0]
            return result

    run_counts = []
    for _ in range(2):
        provisioner.ensure_backup_database(
            backup_db_path=temp_env_with_knowledge_areas["backup_db"],
            source_archive=temp_env_with_knowledge_areas["zip_path"],
            force_rebuild=True,
        )
        merger = BackupDatabaseMerger(provisioner=provisioner)
        merger.merge(
            temp_env_with_knowledge_areas["active_db"],
            temp_env_with_knowledge_areas["backup_db"],
        )
        run_counts.append(counts(temp_env_with_knowledge_areas["active_db"]))

    assert run_counts[0] == {
        "researcher_knowledge_areas": 1,
        "group_knowledge_areas": 1,
        "initiative_knowledge_areas": 1,
    }
    assert run_counts[1] == run_counts[0]


def test_provisioning_seeds_full_historical_campus_catalog(
    temp_env_with_knowledge_areas,
):
    """Spec 011 US1/US3: organizational_units must be seeded from the full
    23-campus historical catalog, not just the 1 row present in the live
    archive's campuses_canonical.json, and must use the historical ids
    (Serra=6, not the previously hardcoded Serra=1)."""
    provisioner = BackupDatabaseProvisioner()
    db_path = provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM organizational_units")
        assert cur.fetchone()[0] == 23

        cur.execute("SELECT name FROM organizational_units WHERE id = 1")
        assert cur.fetchone()[0] == "Vila Velha"

        cur.execute("SELECT name FROM organizational_units WHERE id = 6")
        assert cur.fetchone()[0] == "Serra"

        # No duplicate campus names
        cur.execute(
            "SELECT count(*) FROM (SELECT lower(name) FROM organizational_units GROUP BY lower(name) HAVING count(*) > 1)"
        )
        assert cur.fetchone()[0] == 0


def test_no_dangling_campus_id_after_merge(temp_env_with_knowledge_areas):
    """Spec 011 US1: every research_groups.campus_id must resolve to a real
    row in organizational_units after provisioning and merge."""
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    merger = BackupDatabaseMerger(provisioner=provisioner)
    merger.merge(
        temp_env_with_knowledge_areas["active_db"],
        temp_env_with_knowledge_areas["backup_db"],
    )

    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM research_groups WHERE campus_id NOT IN (SELECT id FROM organizational_units)"
        )
        assert cur.fetchone()[0] == 0

        # research_groups_canonical.json's group "Group A" has campus_id=1,
        # which historically is Vila Velha, not Serra.
        cur.execute(
            "SELECT ou.name FROM research_groups rg JOIN organizational_units ou ON rg.campus_id = ou.id WHERE rg.id = 1"
        )
        assert cur.fetchone()[0] == "Vila Velha"


def test_research_group_organization_id_backfilled(temp_env_with_knowledge_areas):
    """Spec 011 US2: teams.organization_id for research groups must be
    backfilled (historically 1, "Instituto Federal do Espirito Santo") instead
    of staying NULL, since the live archive always carries organization_id=None
    for research groups."""
    provisioner = BackupDatabaseProvisioner()
    db_path = provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT t.organization_id FROM teams t JOIN research_groups rg ON t.id = rg.id WHERE rg.id = 1"
        )
        assert cur.fetchone()[0] == 1


def test_merge_corrects_stale_campus_row_in_active_db(temp_env_with_knowledge_areas):
    """Regression test: an active database that already has the old,
    incorrect campus row (id=1, name='Serra' — the previously hardcoded
    mapping) must have it corrected to the historically accurate value
    ('Vila Velha') after merge, and the historically correct Serra (id=6)
    must be added, not silently dropped by dedup-by-name cleanup."""
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    # Pre-seed the active db with the stale/incorrect campus row, simulating
    # a real production database that predates this fix.
    with sqlite3.connect(str(temp_env_with_knowledge_areas["backup_db"])) as bconn:
        cur = bconn.cursor()
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        )
        schema_sql = "\n".join(row[0] + ";" for row in cur.fetchall())
    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT INTO organizational_units (id, name, organization_id) VALUES (1, 'Serra', 1)"
        )
        conn.commit()

    merger = BackupDatabaseMerger(provisioner=provisioner)
    result = merger.merge(
        temp_env_with_knowledge_areas["active_db"],
        temp_env_with_knowledge_areas["backup_db"],
    )
    assert result["status"] == "success"

    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM organizational_units WHERE id = 1")
        assert cur.fetchone()[0] == "Vila Velha"
        cur.execute("SELECT name FROM organizational_units WHERE id = 6")
        assert cur.fetchone()[0] == "Serra"
        cur.execute("SELECT count(*) FROM organizational_units")
        assert cur.fetchone()[0] == 23


def test_merge_backfills_organization_id_for_preexisting_research_group_team(
    temp_env_with_knowledge_areas,
):
    """Regression test: a research group team that already exists in the
    active database (e.g. created by a live scraper run) with
    organization_id still NULL must be backfilled from the backup on merge,
    since a plain INSERT OR IGNORE never reaches rows that already exist."""
    provisioner = BackupDatabaseProvisioner()
    provisioner.ensure_backup_database(
        backup_db_path=temp_env_with_knowledge_areas["backup_db"],
        source_archive=temp_env_with_knowledge_areas["zip_path"],
        force_rebuild=True,
    )

    with sqlite3.connect(str(temp_env_with_knowledge_areas["backup_db"])) as bconn:
        cur = bconn.cursor()
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        )
        schema_sql = "\n".join(row[0] + ";" for row in cur.fetchall())
    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        conn.executescript(schema_sql)
        conn.execute("INSERT INTO research_groups (id, campus_id) VALUES (1, 1)")
        conn.execute(
            "INSERT INTO teams (id, name, organization_id) VALUES (1, 'Group A', NULL)"
        )
        conn.commit()

    merger = BackupDatabaseMerger(provisioner=provisioner)
    result = merger.merge(
        temp_env_with_knowledge_areas["active_db"],
        temp_env_with_knowledge_areas["backup_db"],
    )
    assert result["status"] == "success"

    with sqlite3.connect(str(temp_env_with_knowledge_areas["active_db"])) as conn:
        cur = conn.cursor()
        cur.execute("SELECT organization_id FROM teams WHERE id = 1")
        assert cur.fetchone()[0] == 1


def test_campus_catalog_is_idempotent_across_repeated_provisioning(
    temp_env_with_knowledge_areas,
):
    """Spec 011 US3: re-provisioning the backup database multiple times must
    not accumulate duplicate campus rows or drift from the 23-row catalog."""
    provisioner = BackupDatabaseProvisioner()

    for _ in range(2):
        db_path = provisioner.ensure_backup_database(
            backup_db_path=temp_env_with_knowledge_areas["backup_db"],
            source_archive=temp_env_with_knowledge_areas["zip_path"],
            force_rebuild=True,
        )
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM organizational_units")
            assert cur.fetchone()[0] == 23


def test_sync_backup_from_active(temp_env):
    merger = BackupDatabaseMerger()
    # Create active DB
    with sqlite3.connect(str(temp_env["active_db"])) as conn:
        conn.execute("CREATE TABLE test_sync (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO test_sync (id, val) VALUES (1, 'active_val')")
        conn.commit()

    ok = merger.sync_backup_from_active(temp_env["active_db"], temp_env["backup_db"])
    assert ok is True
    assert temp_env["backup_db"].is_file()

    with sqlite3.connect(str(temp_env["backup_db"])) as conn:
        cur = conn.cursor()
        cur.execute("SELECT val FROM test_sync WHERE id=1")
        assert cur.fetchone()[0] == "active_val"
