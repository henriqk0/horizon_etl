"""Audit script for the team-id-collision and membership-duplication fixes.

Reports, against a target database:
  - how many team_members rows are still filed under a research group's
    team_id but cannot be verified as a real member of that group (i.e.
    remain classified as collision-contaminated or unresolved), and
  - how many team_members rows are still exact duplicates.

Per specs/014-team-id-collision-fix/spec.md's SC-001, a nonzero
collision-affected count does not necessarily mean the fix failed -- rows
predating every available ground-truth source are deliberately left
unresolved rather than guessed at (see the spec's Assumptions section). This
script exists to make that count visible and trackable, not to assert it
must be zero.
"""

import argparse
import sqlite3

from src.core.logic.team_membership_migration import reattribute_collision_rows


def count_duplicate_team_member_rows(conn: sqlite3.Connection) -> int:
    row = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT team_id, person_id, role_id, COUNT(*) c
            FROM team_members
            GROUP BY team_id, person_id, role_id
            HAVING c > 1
        )
        """).fetchone()
    return row[0]


def count_collision_affected_rows(
    conn: sqlite3.Connection,
    archive_path: str,
) -> tuple[int, int]:
    """Returns (collision_groups_with_unresolved_rows, total_unresolved_rows)
    by running the migration's classification logic in dry-run mode -- rows
    it would reattribute are already fixed by a prior real run; rows it
    still can't classify are what remain to investigate."""
    _collision_groups, _reattributed, unresolved = reattribute_collision_rows(
        conn, archive_path, dry_run=True
    )
    affected_groups = {row["team_id"] for row in unresolved}
    return len(affected_groups), len(unresolved)


def main(argv: "list[str] | None" = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="db/horizon.db", help="Path to the SQLite database"
    )
    parser.add_argument(
        "--archive",
        default="data/exports/novo_backup.zip",
        help="Canonical archive used as a ground-truth source for classification",
    )
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    try:
        duplicate_groups = count_duplicate_team_member_rows(conn)
        affected_groups, unresolved_rows = count_collision_affected_rows(
            conn, args.archive
        )
    finally:
        conn.close()

    print(f"Duplicate team_members row-groups remaining: {duplicate_groups}")
    print(
        f"Research groups with unresolved collision-contaminated rows: {affected_groups}"
    )
    print(f"Total unresolved collision-contaminated rows: {unresolved_rows}")
    if duplicate_groups == 0 and unresolved_rows == 0:
        print("Result: CLEAN -- no known issues remain.")
    else:
        print(
            "Result: PARTIAL -- see specs/014-team-id-collision-fix/spec.md "
            "Assumptions for why some rows may remain unresolved by design."
        )


if __name__ == "__main__":
    main()
