# Contract: `team_membership_migration` module

No external HTTP/CLI API is exposed to other systems by this feature. The relevant contract is the migration function's own guarantees, since it runs directly against the production SQLite database.

## `migrate_team_membership(db_path: str, *, dry_run: bool = False) -> MigrationReport`

**Preconditions**:
- `db_path` points to a SQLite database with the current `research_domain` schema (has `teams`, `team_members`, `research_groups`, `initiatives`, `initiative_teams` tables).
- The canonical archive (`data/exports/novo_backup.zip`, or the currently-exported `research_groups_canonical.json`/`initiatives_canonical.json`) is available for the ground-truth classification step (Decision 5).

**Guarantees**:
- **Idempotent**: running the migration twice in a row produces the same final state as running it once — the second run reports zero additional changes (SC-003 territory, but for the migration itself rather than provisioning).
- **Transactional per collision group**: each research-group/initiative id collision is resolved in its own transaction; a failure partway through leaves already-completed groups migrated and the failing group untouched (not partially migrated).
- **Never deletes a real relationship**: only exact duplicate rows (same `team_id`, `person_id`, `role_id`) are deleted, and only re-pointing (`UPDATE team_members SET team_id = ...`) is used for collision re-attribution, never a delete-and-reinsert that could lose `start_date`/`end_date`.
- **`dry_run=True`** performs every classification and count but issues no `UPDATE`/`DELETE` — returns the same `MigrationReport` that a real run would, for safe preview against production data before committing.
- Returns a `MigrationReport` with: `duplicates_removed`, `collision_groups_found`, `rows_reattributed`, `rows_unresolved` (with enough detail — `team_id`, `person_id` — to manually inspect any unresolved rows).

**Postconditions** (verified by `verify_team_membership_integrity.py`, User Story 3 / FR-006):
- `SELECT COUNT(*) FROM (SELECT team_id, person_id, role_id, COUNT(*) c FROM team_members GROUP BY 1,2,3 HAVING c > 1)` → 0.
- `SELECT COUNT(DISTINCT tm.team_id) FROM team_members tm JOIN research_groups rg ON tm.team_id = rg.id JOIN initiative_teams it ON it.team_id = tm.team_id WHERE it.initiative_id != tm.team_id` type checks confirming no research group's `team_members` still contains a person only attributable to a colliding initiative → 0.

## Provisioner contract change (`backup_db_provisioner.py`)

**Before**: `INSERT OR IGNORE INTO teams (id, name, description) VALUES (initiative.id, ...)` — explicit, colliding id.

**After**: initiative-linked team creation first checks for an existing self-owned team (Decision 3's query); if none exists, inserts a new `teams` row with `id` omitted (auto-assigned) and links it via `initiative_teams`. Idempotent by construction — re-running finds the already-created team and skips creation.

**Backward compatibility**: `canonical_exporter.py` continues to receive correct data through the exact same queries it already runs (`_fetch_person_project_roles`, the advisorship/initiative team export) — those queries join through `initiative_teams`/`team_members` by `team_id`, which still resolves correctly regardless of what specific id was assigned, since they never hardcode the id, only the join relationship.
