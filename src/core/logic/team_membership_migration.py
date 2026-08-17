"""One-time-safe migration for two team_members data-integrity bugs.

1. research_groups and initiatives share the `teams` table, and
   backup_db_provisioner.py used to force teams.id == initiatives.id, which
   collides with teams.id == research_groups.id (research_groups.id is a
   subset of initiatives.id). Every research group's member list was
   contaminated by whichever initiative happened to share its id.
2. team_members has no uniqueness constraint, so two redundant loops in
   backup_db_provisioner.py (an initiative's own team list, and each
   researcher's own initiatives list) each insert the same relationship,
   producing an exact duplicate on every single archive build.

This module cleans up both, safely, against already-corrupted production
data: exact duplicates are deduplicated (keeping the most recent copy), and
rows misattributed to a colliding research group are re-pointed to the
initiative's own (now-disjoint) team — never deleted, never guessed.

Classification is done by normalized person NAME, not raw person_id.
person_consolidator.py/reference_consolidator.py periodically merge
duplicate person records (re-pointing team_members.person_id from a "loser"
id to a "winner" id) without leaving a queryable id-remapping trail, so a
person's id today can differ from what a source archive snapshot recorded
for the same real individual. Confirmed on real data: matching by id alone
left ~86% of collision rows unclassifiable; matching by name resolved the
same rows correctly (e.g. person id 3687 today == "Alessandra Jordão
Bicalho" in the live database, an exact name match to the archive's group-1
member list, despite the archive listing a different, now-superseded id for
that same person).
"""

import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

from src.adapters.sources.lattes_parser import LattesParser

_parser = LattesParser()


def _normalize_name(name: Optional[str]) -> str:
    return _parser.normalize_title(name)


@dataclass
class MigrationReport:
    duplicates_removed: int = 0
    collision_groups_found: int = 0
    rows_reattributed: int = 0
    rows_unresolved: list[dict[str, Any]] = field(default_factory=list)


def load_archive_group_member_names(archive_path: str, group_id: int) -> set[str]:
    """Returns the normalized names of `group_id`'s members in the canonical
    archive's research_groups_canonical.json."""
    with zipfile.ZipFile(archive_path) as zf:
        with zf.open("research_groups_canonical.json") as f:
            groups = json.load(f)
    group = next((g for g in groups if g.get("id") == group_id), None)
    if not group:
        return set()
    return {
        _normalize_name(m.get("name"))
        for m in (group.get("members") or [])
        if isinstance(m, dict) and m.get("name")
    }


def load_archive_initiative_team_names(
    archive_path: str, initiative_id: int
) -> set[str]:
    """Returns the normalized names on `initiative_id`'s team in the
    canonical archive's initiatives_canonical.json."""
    with zipfile.ZipFile(archive_path) as zf:
        with zf.open("initiatives_canonical.json") as f:
            initiatives = json.load(f)
    initiative = next((i for i in initiatives if i.get("id") == initiative_id), None)
    if not initiative:
        return set()
    return {
        _normalize_name(m.get("person_name"))
        for m in (initiative.get("team") or [])
        if isinstance(m, dict) and m.get("person_name")
    }


def load_live_synced_group_member_names(
    conn: sqlite3.Connection, group_id: int
) -> set[str]:
    """Returns the normalized names of people independently confirmed as
    real members of `group_id` via a live sync's entity_change_logs trail
    (e.g. CNPq group sync), regardless of what the static archive snapshot
    contains. Resolves each logged person_id to its CURRENT name, so this
    is immune to any id drift from person-record consolidation happening
    after the change was logged."""
    rows = conn.execute(
        """
        SELECT after_json FROM entity_change_logs
        WHERE canonical_entity_type = 'research_group'
          AND canonical_entity_id = ?
          AND operation = 'update'
        """,
        (group_id,),
    ).fetchall()
    names: set[str] = set()
    for (after_json,) in rows:
        if not after_json:
            continue
        try:
            payload = json.loads(after_json)
        except (TypeError, ValueError):
            continue
        person_id = payload.get("person_id")
        if person_id is None:
            continue
        name_row = conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if name_row and name_row[0]:
            names.add(_normalize_name(name_row[0]))
    return names


def deduplicate_team_members(conn: sqlite3.Connection, *, dry_run: bool = False) -> int:
    """Deletes exact duplicate (team_id, person_id, role_id) rows, keeping
    only the highest-id (most recent) copy of each. Returns the number of
    rows removed (or that would be removed, if dry_run)."""
    duplicate_groups = conn.execute("""
        SELECT team_id, person_id, role_id, COUNT(*) as cnt
        FROM team_members
        GROUP BY team_id, person_id, role_id
        HAVING cnt > 1
        """).fetchall()

    removed = 0
    for team_id, person_id, role_id, _cnt in duplicate_groups:
        ids = [
            row[0]
            for row in conn.execute(
                """
                SELECT id FROM team_members
                WHERE team_id = ? AND person_id = ? AND role_id IS ?
                ORDER BY id DESC
                """,
                (team_id, person_id, role_id),
            ).fetchall()
        ]
        stale_ids = ids[1:]
        removed += len(stale_ids)
        if not dry_run and stale_ids:
            conn.executemany(
                "DELETE FROM team_members WHERE id = ?",
                [(i,) for i in stale_ids],
            )
    return removed


def _find_or_create_initiative_team(
    conn: sqlite3.Connection, initiative_id: int, *, dry_run: bool = False
) -> Optional[int]:
    """Idempotent lookup/creation of an initiative's own (disjoint) team id.

    Reuses the same "team_id not owned by a research group" predicate as
    canonical_exporter.py's existing _fetch_person_project_roles guard, so
    an initiative already linked to its sponsoring research group's team is
    never mistaken for the initiative's own team.
    """
    existing = conn.execute(
        """
        SELECT team_id FROM initiative_teams
        WHERE initiative_id = ?
          AND team_id NOT IN (SELECT id FROM research_groups)
        LIMIT 1
        """,
        (initiative_id,),
    ).fetchone()
    if existing:
        return existing[0]

    if dry_run:
        return None

    row = conn.execute(
        "SELECT name, description FROM initiatives WHERE id = ?", (initiative_id,)
    ).fetchone()
    name = row[0] if row else f"Initiative {initiative_id}"
    description = row[1] if row else None
    cur = conn.execute(
        "INSERT INTO teams (name, description) VALUES (?, ?)", (name, description)
    )
    new_team_id = cur.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO initiative_teams (initiative_id, team_id) VALUES (?, ?)",
        (initiative_id, new_team_id),
    )
    return new_team_id


def reattribute_collision_rows(
    conn: sqlite3.Connection, archive_path: str, *, dry_run: bool = False
) -> tuple[int, int, list[dict[str, Any]]]:
    """Classifies and re-attributes team_members rows filed under a team_id
    that collides between a research group and an initiative. Returns
    (collision_groups_found, rows_reattributed, unresolved_rows)."""
    colliding_ids = [row[0] for row in conn.execute("""
            SELECT id FROM research_groups
            WHERE id IN (SELECT id FROM initiatives)
            """).fetchall()]

    rows_reattributed = 0
    unresolved: list[dict[str, Any]] = []

    for group_id in colliding_ids:
        initiative_id = group_id  # same numeric id, by definition of the collision

        try:
            archive_group_names = load_archive_group_member_names(
                archive_path, group_id
            )
        except (FileNotFoundError, KeyError):
            archive_group_names = set()
        try:
            archive_initiative_names = load_archive_initiative_team_names(
                archive_path, initiative_id
            )
        except (FileNotFoundError, KeyError):
            archive_initiative_names = set()
        live_group_names = load_live_synced_group_member_names(conn, group_id)
        real_group_names = archive_group_names | live_group_names

        member_rows = conn.execute(
            """
            SELECT tm.id, tm.person_id, tm.role_id, p.name
            FROM team_members tm
            LEFT JOIN persons p ON p.id = tm.person_id
            WHERE tm.team_id = ?
            """,
            (group_id,),
        ).fetchall()

        rows_to_move: list[int] = []  # team_members.id
        for tm_id, person_id, role_id, person_name in member_rows:
            normalized_name = _normalize_name(person_name)
            if normalized_name and normalized_name in real_group_names:
                continue  # correctly attributed, leave in place
            if normalized_name and normalized_name in archive_initiative_names:
                rows_to_move.append(tm_id)
            else:
                unresolved.append(
                    {
                        "team_members_id": tm_id,
                        "team_id": group_id,
                        "person_id": person_id,
                        "role_id": role_id,
                    }
                )

        if not rows_to_move:
            continue

        target_team_id = _find_or_create_initiative_team(
            conn, initiative_id, dry_run=dry_run
        )
        if target_team_id is None:
            # dry_run with no pre-existing team: nothing to point to yet,
            # still count the rows that would be moved.
            rows_reattributed += len(rows_to_move)
            continue

        if not dry_run:
            conn.executemany(
                "UPDATE team_members SET team_id = ? WHERE id = ?",
                [(target_team_id, tm_id) for tm_id in rows_to_move],
            )
        rows_reattributed += len(rows_to_move)

    return len(colliding_ids), rows_reattributed, unresolved


def prune_unverified_group_memberships(
    conn: sqlite3.Connection, archive_path: str, *, dry_run: bool = False
) -> tuple[int, int]:
    """Removes team_members rows filed under a RESEARCH GROUP's team id when
    the person cannot be verified as a real member of that group by either
    ground-truth source: the canonical archive's own member list for that
    group, or a live CNPq sync recorded in entity_change_logs.

    Returns (rows_removed, rows_kept).

    Why deletion is correct here (unlike the collision re-attribution, which
    only ever moves rows): a row under a research group asserts "this person
    is a member of this group". The canonical archive IS the authoritative
    export of that group's real membership, and entity_change_logs covers
    anyone who joined after that snapshot. A person in neither is an
    artifact of the teams.id collision (an unrelated initiative's team
    member filed under the group's id), so the assertion is simply false.
    Measured on production: 26,831 of 41,612 group memberships (65%) were
    unverifiable this way, which is what inflated every group's roster and,
    because a person's campus is derived from their group, put thousands of
    people on the wrong campus.

    Only the group association is removed. The person, their initiative and
    advisorship memberships, and every non-research-group team row are left
    untouched.
    """
    archive_names: dict[int, set[str]] = {}
    with zipfile.ZipFile(archive_path) as zf:
        with zf.open("research_groups_canonical.json") as f:
            for group in json.load(f):
                gid = group.get("id")
                if gid is None:
                    continue
                archive_names[gid] = {
                    _normalize_name(m.get("name"))
                    for m in (group.get("members") or [])
                    if isinstance(m, dict) and m.get("name")
                }

    live_ids: dict[int, set[int]] = {}
    for gid, after_json in conn.execute(
        "SELECT canonical_entity_id, after_json FROM entity_change_logs "
        "WHERE canonical_entity_type = 'research_group' AND operation = 'update'"
    ).fetchall():
        if not after_json:
            continue
        try:
            person_id = json.loads(after_json).get("person_id")
        except (TypeError, ValueError):
            continue
        if person_id is not None:
            live_ids.setdefault(gid, set()).add(person_id)

    stale_ids: list[int] = []
    kept = 0
    for (group_id,) in conn.execute("SELECT id FROM research_groups").fetchall():
        verified_names = archive_names.get(group_id, set())
        verified_ids = live_ids.get(group_id, set())
        for tm_id, person_id, person_name in conn.execute(
            "SELECT tm.id, tm.person_id, p.name FROM team_members tm "
            "LEFT JOIN persons p ON p.id = tm.person_id WHERE tm.team_id = ?",
            (group_id,),
        ).fetchall():
            if _normalize_name(person_name) in verified_names or person_id in verified_ids:
                kept += 1
            else:
                stale_ids.append(tm_id)

    if not dry_run and stale_ids:
        conn.executemany(
            "DELETE FROM team_members WHERE id = ?", [(i,) for i in stale_ids]
        )

    return len(stale_ids), kept


def migrate_team_membership(
    db_path: str,
    *,
    archive_path: str = "data/exports/novo_backup.zip",
    dry_run: bool = False,
) -> MigrationReport:
    """Top-level entrypoint: deduplicates team_members, then re-attributes
    id-collision-contaminated rows to their correct (disjoint) initiative
    team. Never deletes a real relationship.

    NOTE: an earlier revision accepted a `third_party_db_path` to use an
    older sibling database as an extra ground-truth source. That was
    REMOVED after it corrupted production data: it copied `team_id` values
    straight across databases, but team ids are NOT portable between them
    (verified: team 92 is "agroecologia" in the old snapshot and
    "Alfabetização Científica" in the current one; 106, 150, 188 and 344
    likewise differ). Because a person's campus is derived from their
    research group, that mis-mapped ~9,400 memberships onto unrelated
    groups and silently moved people to the wrong campus. Any future
    cross-database source MUST resolve teams by NAME, never by id, and be
    validated against a scratch copy before being applied.
    """
    conn = sqlite3.connect(db_path)
    try:
        # Existing duplicates must be removed BEFORE the unique index is
        # created below -- SQLite refuses to build a unique index over data
        # that already violates it.
        duplicates_removed = deduplicate_team_members(conn, dry_run=dry_run)
        collision_groups_found, rows_reattributed, unresolved = (
            reattribute_collision_rows(conn, archive_path, dry_run=dry_run)
        )

        # Re-attribution can itself introduce a fresh duplicate: a row moved
        # to an initiative's disjoint team can land on the exact same
        # (team_id, person_id, role_id) as a row already there (e.g. from a
        # live sync). Run dedup again to catch that before the index below.
        duplicates_removed += deduplicate_team_members(conn, dry_run=dry_run)
        if not dry_run:
            # Permanently fixes the schema on databases built before this
            # feature existed, so every future INSERT OR IGNORE against
            # team_members (here and in backup_db_provisioner.py) actually
            # suppresses duplicates going forward.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_team_members_team_person_role "
                "ON team_members(team_id, person_id, role_id)"
            )
            conn.commit()
        return MigrationReport(
            duplicates_removed=duplicates_removed,
            collision_groups_found=collision_groups_found,
            rows_reattributed=rows_reattributed,
            rows_unresolved=unresolved,
        )
    finally:
        conn.close()
