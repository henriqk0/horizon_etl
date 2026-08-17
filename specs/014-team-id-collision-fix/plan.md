# Implementation Plan: Team ID Collision & Membership Duplication Fix

**Branch**: `014-team-id-collision-fix` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-team-id-collision-fix/spec.md`

## Summary

`teams` is a single shared table backing two conceptually distinct things: a research group's own team (`research_groups.id == teams.id`, correct joined-table inheritance) and an initiative's own team (`backup_db_provisioner.py` forces `teams.id == initiatives.id`, a plain shortcut with no inheritance backing it). Since `research_groups.id` (1–344) and `initiatives.id` (1–7962) are independent sequences, every research group's id also exists as an initiative id — 344 of 344 (100%) collide. Both a research group's real members and the colliding initiative's real team members end up filed under the same `team_id`, so every research-group member list (and the campus/context derived from it) is contaminated by an unrelated project's team. Separately, three `INSERT OR IGNORE INTO team_members (team_id, person_id, role_id)` call sites in the same file omit the `id` column, so SQLite auto-assigns a fresh row id on every provisioning run regardless of whether the same relationship already exists — `team_members` has no `UNIQUE` constraint besides the surrogate `id`, so "OR IGNORE" never actually suppresses anything. Confirmed on the live database: 14,814 of 62,949 rows (23.5%) are exact duplicates.

The fix has three parts: (1) give initiative-linked teams their own disjoint id space so they never collide with `research_groups.id` again, (2) add a real uniqueness constraint on `team_members` so re-provisioning is genuinely idempotent going forward, (3) a one-time, in-place migration that deduplicates existing rows and re-attributes existing collision-contaminated rows to the correct (now-disjoint) team, using the canonical archive and CNPq-sync provenance as ground truth — without deleting any real membership.

## Technical Context

**Language/Version**: Python ≥3.10 (project-wide constraint), SQLite (`db/horizon.db`, `data/backup/horizon_backup.db`)

**Primary Dependencies**: `sqlite3` (stdlib, already used directly by `backup_db_provisioner.py`/`backup_merger.py` for raw SQL), no new dependencies

**Storage**: SQLite — this feature is a schema + data migration on the existing `teams`, `team_members`, `initiative_teams` tables. No new tables.

**Testing**: pytest (project standard). Migration logic tested against synthetic in-memory SQLite databases; the collision-detection and dedup logic covered by unit tests before being run against the real database.

**Target Platform**: Linux server (same execution environment as the rest of the ETL)

**Project Type**: Single project — internal ETL library/CLI (`src/core/logic/`)

**Performance Goals**: The one-time migration must complete in well under a minute against the current ~63k-row `team_members` table (this is a simple table, not the multi-hundred-thousand-row scale of the graph-export work in spec 013). The idempotency fix itself must not measurably slow down `backup_db_provisioner.py`'s normal run time.

**Constraints**:
- A research group's public identifier (`research_groups.id` / `teams.id`) MUST NOT change (FR-003) — Dashboard links already reference these ids.
- `canonical_exporter.py`'s existing queries (`_fetch_person_project_roles`, `_fetch_person_research_group_roles`, the researcher-enrichment group query, and the line-2232 query) must keep working correctly against the corrected schema — verified by re-reading each query as part of this plan (see research.md Decision 4).
- The fix must be safely re-runnable against the *already-migrated* database (the migration itself must be idempotent, since it may need to run again if a future regression reintroduces some duplicates).

**Scale/Scope**: 344 research groups, 7,962 initiatives, 344 confirmed id collisions (100% of groups), 62,949 `team_members` rows (14,814 confirmed duplicates, 152 of the duplicate pairs differing in role).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Ports & Adapters Architecture**: PASS. Entirely within `src/core/logic/` (provisioner + a new migration module); no adapter changes.
- **II. Domain-First Data Modeling**: PASS. No new entity types — this corrects the *mapping* of existing entities (Team, TeamMember) onto the shared `teams` table, it doesn't invent new domain concepts.
- **III. Prefect Flow Orchestration**: PASS. The migration runs as a step inside the existing backup-provisioning task, which already executes inside a Prefect flow context (`weekly_orchestrator.py`).
- **IV. Audit-Driven Data Quality**: PASS — directly serves this principle. User Story 3 (verification check) and FR-006 exist specifically to make this fix auditable, matching the `unresolved_count`-style reporting pattern already established for research group institutional filtering (spec 011).
- **V. LGPD Compliance by Default**: PASS. No new personal-data fields; this only corrects which existing (already-anonymization-compliant) records are associated with which team.
- **Development Workflow & Quality Gates**: New/modified code MUST pass `make ci-check`. The migration script is new ingestion-adjacent logic — it gets a corresponding audit/verification check per Principle IV, satisfied by User Story 3.

No violations requiring justification — Complexity Tracking section is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/014-team-id-collision-fix/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/             # Phase 1 output (migration contract, not an API)
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/core/logic/
├── backup_db_provisioner.py          # MODIFIED — initiative teams get a disjoint id (no longer teams.id == initiatives.id); team_members inserts become genuinely idempotent
├── team_membership_migration.py      # NEW — one-time-safe migration: dedup existing team_members rows, re-attribute collision-contaminated rows to a disjoint initiative team id
└── canonical_exporter.py             # MODIFIED — apply the same "exclude ids that are also research_groups.id" defensive guard (already used in _fetch_person_project_roles) to the research-group member queries too, as defense in depth

src/scripts/
└── verify_team_membership_integrity.py   # NEW — audit script per FR-006/User Story 3: reports remaining id-collision count and duplicate-row count

app.py
└── (MODIFIED) new CLI command to run the migration explicitly against a target database, mirroring the existing `init_backup_db`/`merge_backup` commands

tests/
├── test_team_membership_migration.py     # NEW — unit tests for the dedup + re-attribution logic against synthetic SQLite databases
├── test_backup_db_provisioner.py         # MODIFIED (create if absent) — assert initiative teams no longer collide with research_groups.id, assert re-running provisioning doesn't grow team_members
└── test_verify_team_membership_integrity.py  # NEW — unit tests for the audit script's counts
```

**Structure Decision**: Single project, consistent with the rest of `src/core/logic/`. The migration is deliberately a separate, standalone module (`team_membership_migration.py`) rather than inline code in the provisioner, so it can be run independently against the live database via a CLI command — this migration needs to run once against already-corrupted production data, which is a different concern from the ongoing provisioning-idempotency fix.

## Complexity Tracking

*No constitution violations — table not needed.*
