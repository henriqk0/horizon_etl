import json
import sqlite3
import zipfile

from src.core.logic.team_membership_migration import (
    MigrationReport,
    deduplicate_team_members,
    load_archive_group_member_names,
    load_archive_initiative_team_names,
    load_live_synced_group_member_names,
    migrate_team_membership,
    prune_unverified_group_memberships,
    reattribute_collision_rows,
)


def _make_archive(tmp_path, groups, initiatives, filename="archive.zip"):
    path = tmp_path / filename
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("research_groups_canonical.json", json.dumps(groups))
        zf.writestr("initiatives_canonical.json", json.dumps(initiatives))
    return str(path)


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


# --- ground-truth loaders ---


def test_load_archive_group_member_names(tmp_path):
    archive = _make_archive(
        tmp_path,
        groups=[
            {
                "id": 9,
                "name": "G",
                "members": [
                    {"id": 1, "name": "Ana Silva"},
                    {"id": 2, "name": "Bruno Reis"},
                ],
            }
        ],
        initiatives=[],
    )
    assert load_archive_group_member_names(archive, 9) == {"ana silva", "bruno reis"}
    assert load_archive_group_member_names(archive, 999) == set()


def test_load_archive_initiative_team_names(tmp_path):
    archive = _make_archive(
        tmp_path,
        groups=[],
        initiatives=[
            {
                "id": 9,
                "name": "I",
                "team": [
                    {"person_id": 456, "person_name": "Paulo Sérgio Dos Santos Júnior"},
                    {"person_id": 531, "person_name": "Fabiano Borges Ruy"},
                ],
            }
        ],
    )
    assert load_archive_initiative_team_names(archive, 9) == {
        "paulo sergio dos santos junior",
        "fabiano borges ruy",
    }
    assert load_archive_initiative_team_names(archive, 999) == set()


def test_load_live_synced_group_member_names():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO persons (id, name) VALUES (1136, 'Nova Pessoa Sincronizada')"
    )
    conn.execute(
        "INSERT INTO entity_change_logs (canonical_entity_type, canonical_entity_id, operation, after_json) "
        "VALUES ('research_group', 9, 'update', ?)",
        (json.dumps({"person_id": 1136, "role_id": 7}),),
    )
    conn.execute(
        "INSERT INTO entity_change_logs (canonical_entity_type, canonical_entity_id, operation, after_json) "
        "VALUES ('research_group', 9, 'update', ?)",
        (
            json.dumps({"start_date": "2016-01-01"}),
        ),  # no person_id, e.g. group-level update
    )
    assert load_live_synced_group_member_names(conn, 9) == {"nova pessoa sincronizada"}


# --- deduplicate_team_members ---


def test_deduplicate_keeps_highest_id_row():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (4, 1, 456, 9)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (14826, 1, 456, 9)"
    )

    removed = deduplicate_team_members(conn)

    assert removed == 1
    remaining = conn.execute("SELECT id FROM team_members").fetchall()
    assert remaining == [(14826,)]


def test_deduplicate_resolves_role_conflicting_duplicates_to_most_recent():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (185, 9, 1136, 7)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (99999, 9, 1136, 8)"
    )

    removed = deduplicate_team_members(conn)

    # Different role_id means these are NOT grouped as duplicates by
    # (team_id, person_id, role_id) — both distinct roles are preserved.
    assert removed == 0
    remaining = {
        row[0] for row in conn.execute("SELECT id FROM team_members").fetchall()
    }
    assert remaining == {185, 99999}


def test_deduplicate_dry_run_does_not_delete():
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (2, 1, 1, 1)"
    )

    removed = deduplicate_team_members(conn, dry_run=True)

    assert removed == 1
    assert conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0] == 2


# --- reattribute_collision_rows ---


def _seed_collision_fixture(conn):
    _base_schema(conn)
    conn.execute("INSERT INTO research_groups (id) VALUES (9)")
    conn.execute(
        "INSERT INTO teams (id, name) VALUES (9, 'Aquicultura e Ambiencia Animal')"
    )
    conn.execute(
        "INSERT INTO initiatives (id, name, description) VALUES (9, 'ConectaFAPES', NULL)"
    )
    conn.execute("INSERT INTO initiative_teams (initiative_id, team_id) VALUES (9, 9)")
    conn.execute("INSERT INTO persons (id, name) VALUES (281, 'Real Group Member')")
    conn.execute(
        "INSERT INTO persons (id, name) VALUES (456, 'Paulo Sergio Dos Santos Junior')"
    )
    # real group member
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 9, 281, 7)"
    )
    # real initiative member (Paulo Sergio), mistakenly under the group's team_id
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (2, 9, 456, 9)"
    )
    conn.commit()


def _archive_with_real_membership(tmp_path, filename="archive.zip"):
    return _make_archive(
        tmp_path,
        groups=[
            {
                "id": 9,
                "name": "G",
                "members": [{"id": 281, "name": "Real Group Member"}],
            }
        ],
        initiatives=[
            {
                "id": 9,
                "name": "I",
                "team": [
                    {"person_id": 456, "person_name": "Paulo Sergio Dos Santos Junior"}
                ],
            }
        ],
        filename=filename,
    )


def test_reattribute_moves_initiative_members_off_the_colliding_group_id(tmp_path):
    archive = _archive_with_real_membership(tmp_path)
    conn = sqlite3.connect(":memory:")
    _seed_collision_fixture(conn)

    collision_groups, reattributed, unresolved = reattribute_collision_rows(
        conn, archive
    )

    assert collision_groups == 1
    assert reattributed == 1
    assert unresolved == []

    # Real group member stays under the group's id (unchanged, per FR-003).
    group_members = {
        row[0]
        for row in conn.execute(
            "SELECT person_id FROM team_members WHERE team_id = 9"
        ).fetchall()
    }
    assert group_members == {281}

    # Paulo Sergio's row moved to a NEW, disjoint team id -- never deleted (FR-002).
    all_person_ids = {
        row[0] for row in conn.execute("SELECT person_id FROM team_members").fetchall()
    }
    assert 456 in all_person_ids
    new_team_id = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 456"
    ).fetchone()[0]
    assert new_team_id != 9

    # The initiative now links to that new disjoint team.
    linked_team_ids = {
        row[0]
        for row in conn.execute(
            "SELECT team_id FROM initiative_teams WHERE initiative_id = 9"
        ).fetchall()
    }
    assert new_team_id in linked_team_ids


def test_reattribute_matches_by_name_despite_person_id_drift(tmp_path):
    """The real bug found during validation: a person's id in the live db
    can differ from what the archive recorded (due to person_consolidator.py
    merges), but the name is stable -- classification must use it."""
    archive = _make_archive(
        tmp_path,
        groups=[
            {
                "id": 9,
                "name": "G",
                "members": [{"id": 9999999, "name": "Real Group Member"}],
            }
        ],
        initiatives=[
            {
                "id": 9,
                "name": "I",
                # Archive recorded a now-superseded id for the same real person.
                "team": [
                    {
                        "person_id": 8888888,
                        "person_name": "Paulo Sergio Dos Santos Junior",
                    }
                ],
            }
        ],
    )
    conn = sqlite3.connect(":memory:")
    _seed_collision_fixture(conn)  # live db has person_id 456, not 8888888

    collision_groups, reattributed, unresolved = reattribute_collision_rows(
        conn, archive
    )

    assert reattributed == 1
    assert unresolved == []
    new_team_id = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 456"
    ).fetchone()[0]
    assert new_team_id != 9


def test_reattribute_dry_run_does_not_modify_data(tmp_path):
    archive = _archive_with_real_membership(tmp_path)
    conn = sqlite3.connect(":memory:")
    _seed_collision_fixture(conn)

    collision_groups, reattributed, unresolved = reattribute_collision_rows(
        conn, archive, dry_run=True
    )

    assert reattributed == 1
    row = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 456"
    ).fetchone()
    assert row[0] == 9  # unchanged


def test_reattribute_leaves_unresolved_rows_untouched(tmp_path):
    archive = _make_archive(
        tmp_path,
        groups=[
            {
                "id": 9,
                "name": "G",
                "members": [{"id": 281, "name": "Real Group Member"}],
            }
        ],
        initiatives=[
            {"id": 9, "name": "I", "team": []}
        ],  # Paulo absent from both lists
    )
    conn = sqlite3.connect(":memory:")
    _seed_collision_fixture(conn)

    collision_groups, reattributed, unresolved = reattribute_collision_rows(
        conn, archive
    )

    assert reattributed == 0
    assert len(unresolved) == 1
    assert unresolved[0]["person_id"] == 456
    # Row is left exactly where it was -- never guess-deleted.
    row = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 456"
    ).fetchone()
    assert row[0] == 9


def test_reattribute_reuses_existing_disjoint_team_on_second_run(tmp_path):
    archive = _archive_with_real_membership(tmp_path)
    conn = sqlite3.connect(":memory:")
    _seed_collision_fixture(conn)

    reattribute_collision_rows(conn, archive)
    first_new_team_id = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 456"
    ).fetchone()[0]

    # Add another initiative-team member row directly under the colliding id,
    # simulating a fresh provisioning run before this fix existed.
    conn.execute("INSERT INTO persons (id, name) VALUES (531, 'Fabiano Borges Ruy')")
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (3, 9, 531, 9)"
    )
    archive2 = _make_archive(
        tmp_path,
        groups=[
            {
                "id": 9,
                "name": "G",
                "members": [{"id": 281, "name": "Real Group Member"}],
            }
        ],
        initiatives=[
            {
                "id": 9,
                "name": "I",
                "team": [
                    {"person_id": 456, "person_name": "Paulo Sergio Dos Santos Junior"},
                    {"person_id": 531, "person_name": "Fabiano Borges Ruy"},
                ],
            }
        ],
        filename="archive2.zip",
    )
    reattribute_collision_rows(conn, archive2)
    second_new_team_id = conn.execute(
        "SELECT team_id FROM team_members WHERE person_id = 531"
    ).fetchone()[0]

    assert second_new_team_id == first_new_team_id


# --- migrate_team_membership (top-level orchestrator) ---


def test_migrate_team_membership_end_to_end(tmp_path):
    archive = _archive_with_real_membership(tmp_path)
    db_path = str(tmp_path / "scratch.db")
    conn = sqlite3.connect(db_path)
    _seed_collision_fixture(conn)
    # Also seed an exact duplicate to be caught by the dedup half.
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (5, 9, 281, 7)"
    )
    conn.commit()
    conn.close()

    report = migrate_team_membership(db_path, archive_path=archive)

    assert isinstance(report, MigrationReport)
    assert report.duplicates_removed == 1
    assert report.collision_groups_found == 1
    assert report.rows_reattributed == 1
    assert report.rows_unresolved == []

    conn = sqlite3.connect(db_path)
    group_members = {
        row[0]
        for row in conn.execute(
            "SELECT person_id FROM team_members WHERE team_id = 9"
        ).fetchall()
    }
    assert group_members == {281}


# --- prune_unverified_group_memberships ---


def _seed_prune_fixture(conn):
    _base_schema(conn)
    conn.execute("INSERT INTO research_groups (id) VALUES (9)")
    conn.execute("INSERT INTO teams (id, name) VALUES (9, 'Serra Group')")
    conn.execute("INSERT INTO teams (id, name) VALUES (900, 'Some Initiative Team')")
    conn.execute("INSERT INTO persons (id, name) VALUES (1, 'Real Archive Member')")
    conn.execute("INSERT INTO persons (id, name) VALUES (2, 'Live Synced Member')")
    conn.execute("INSERT INTO persons (id, name) VALUES (3, 'Contaminating Person')")
    # all three currently filed under the research group
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 9, 1, 1)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (2, 9, 2, 1)"
    )
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (3, 9, 3, 1)"
    )
    # a non-research-group row that must never be touched
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (4, 900, 3, 1)"
    )
    # person 2 confirmed by a live CNPq sync, not by the archive
    conn.execute(
        "INSERT INTO entity_change_logs (canonical_entity_type, canonical_entity_id, operation, after_json) "
        "VALUES ('research_group', 9, 'update', ?)",
        (json.dumps({"person_id": 2, "role_id": 1}),),
    )
    conn.commit()


def test_prune_removes_only_unverifiable_group_memberships(tmp_path):
    archive = _make_archive(
        tmp_path,
        groups=[
            {"id": 9, "name": "Serra Group", "members": [{"id": 1, "name": "Real Archive Member"}]}
        ],
        initiatives=[],
    )
    conn = sqlite3.connect(":memory:")
    _seed_prune_fixture(conn)

    removed, kept = prune_unverified_group_memberships(conn, archive)

    assert removed == 1  # only the contaminating person
    assert kept == 2  # archive member + live-synced member

    remaining = {
        r[0]
        for r in conn.execute(
            "SELECT person_id FROM team_members WHERE team_id = 9"
        ).fetchall()
    }
    assert remaining == {1, 2}

    # The person's membership on the unrelated (non-group) team survives.
    assert conn.execute(
        "SELECT COUNT(*) FROM team_members WHERE team_id = 900 AND person_id = 3"
    ).fetchone()[0] == 1
    # The person record itself is never deleted.
    assert conn.execute("SELECT COUNT(*) FROM persons WHERE id = 3").fetchone()[0] == 1


def test_prune_dry_run_reports_without_deleting(tmp_path):
    archive = _make_archive(
        tmp_path,
        groups=[
            {"id": 9, "name": "Serra Group", "members": [{"id": 1, "name": "Real Archive Member"}]}
        ],
        initiatives=[],
    )
    conn = sqlite3.connect(":memory:")
    _seed_prune_fixture(conn)

    removed, kept = prune_unverified_group_memberships(conn, archive, dry_run=True)

    assert removed == 1
    assert kept == 2
    assert conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0] == 4


def test_prune_matches_archive_members_by_normalized_name(tmp_path):
    """Accents/case must not cause a real member to be pruned -- person ids
    drift across consolidation merges, so names are the matching key."""
    archive = _make_archive(
        tmp_path,
        groups=[{"id": 9, "name": "G", "members": [{"id": 99, "name": "José da Silva"}]}],
        initiatives=[],
    )
    conn = sqlite3.connect(":memory:")
    _base_schema(conn)
    conn.execute("INSERT INTO research_groups (id) VALUES (9)")
    conn.execute("INSERT INTO teams (id, name) VALUES (9, 'G')")
    conn.execute("INSERT INTO persons (id, name) VALUES (5, 'JOSE DA SILVA')")
    conn.execute(
        "INSERT INTO team_members (id, team_id, person_id, role_id) VALUES (1, 9, 5, 1)"
    )

    removed, kept = prune_unverified_group_memberships(conn, archive)

    assert removed == 0
    assert kept == 1
