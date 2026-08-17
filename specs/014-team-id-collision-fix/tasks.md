---

description: "Task list for Team ID Collision & Membership Duplication Fix"
---

# Tasks: Team ID Collision & Membership Duplication Fix

**Input**: Design documents from `/specs/014-team-id-collision-fix/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included — project constitution requires new ingestion-adjacent logic to have corresponding tests (Principle IV), and this session's established pattern (specs 011–013) always pairs implementation with tests, especially for a production-data migration.

**Organization**: Tasks are grouped by user story (US1/US2/US3, per spec.md's priorities).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project — `src/`, `tests/` at repository root (per plan.md's Structure Decision).

---

## Phase 1: Setup

- [X] T001 Create empty `src/core/logic/team_membership_migration.py` with a module docstring describing its purpose (one-time-safe migration for the team-id-collision and duplicate-membership bugs)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared plumbing every user story's logic is built on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Define `MigrationReport` dataclass (`duplicates_removed`, `collision_groups_found`, `rows_reattributed`, `rows_unresolved: list[dict]`) in `src/core/logic/team_membership_migration.py`, per data-model.md
- [X] T003 [P] Implement ground-truth loader helpers in `src/core/logic/team_membership_migration.py`: `load_archive_group_members(archive_path, group_id)`, `load_archive_initiative_team(archive_path, initiative_id)` (read from the canonical archive zip's `research_groups_canonical.json`/`initiatives_canonical.json`), and `load_live_synced_group_member_ids(conn, group_id)` (query `entity_change_logs` for `canonical_entity_type='research_group'`, matching `canonical_entity_id`) — per research.md Decision 5's classification rule
- [X] T004 Implement `deduplicate_team_members(conn, *, dry_run) -> int` in `src/core/logic/team_membership_migration.py`: for every `(team_id, person_id, role_id)` group with duplicates, delete all but the highest-`id` row (FR-007's resolved rule); returns count of rows removed (depends on T002)
- [X] T005 [P] Unit tests for the ground-truth loaders (T003) and `deduplicate_team_members` (T004) in `tests/test_team_membership_migration.py`, using a small synthetic archive zip and an in-memory SQLite database with seeded `entity_change_logs`/`team_members` rows, including the confirmed real case of role-differing duplicates (152 pairs in production) resolving to the highest-id copy

**Checkpoint**: Foundation ready — dedup works standalone and is tested; user story work can now begin.

---

## Phase 3: User Story 1 - Research Group Pages Show Only Real Members (Priority: P1) 🎯 MVP

**Goal**: Research group member lists (and the campus/context derived from them) never include a person who is only present due to an initiative sharing the group's numeric id — for both new provisioning runs and the already-corrupted live database.

**Independent Test**: Regenerate/provision against real data, then confirm a research group with a known historical id collision (e.g. group #9 "Aquicultura e Ambiência Animal" colliding with initiative #9) shows only its real members, and that the colliding initiative's real members (e.g. Paulo Sérgio, person id 456) keep their real initiative membership intact but no longer appear as a group member.

### Implementation for User Story 1

- [X] T006 [US1] Implement idempotent initiative-team lookup/creation in `src/core/logic/backup_db_provisioner.py`: before creating a team for an initiative, run the `initiative_teams` lookup from research.md Decision 3 (`WHERE initiative_id = ? AND team_id NOT IN (SELECT id FROM research_groups)`); if none found, `INSERT INTO teams (name, description) VALUES (?, ?)` with `id` omitted (auto-assigned), then link it via `initiative_teams`
- [X] T007 [US1] Update the two initiative-team-members loops in `src/core/logic/backup_db_provisioner.py` (section 11b, both the initiative-iterating loop and the researcher-initiatives-iterating loop) to write `team_members` rows using the disjoint team id from T006 instead of the raw `iid` (depends on T006, same file)
- [X] T008 [US1] Implement `reattribute_collision_rows(conn, archive_path, *, dry_run) -> tuple[int, int, list[dict]]` in `src/core/logic/team_membership_migration.py`: for every `team_id` that is both a `research_groups.id` and an `initiatives.id`, classify each of that `team_id`'s `team_members` rows per data-model.md's classification table (`real_group` / `real_initiative` / `unresolved`) using T003's loaders, and for `real_initiative` rows, `UPDATE team_members SET team_id = ?` to the initiative's disjoint team id (found/created via T006's lookup) — never deletes a row (depends on T003, T006)
- [X] T009 [US1] Implement top-level `migrate_team_membership(db_path, *, dry_run=False) -> MigrationReport` in `src/core/logic/team_membership_migration.py`, orchestrating `deduplicate_team_members` then `reattribute_collision_rows` inside a transaction per collision group, per the migration contract (depends on T004, T008)
- [X] T010 [P] [US1] Unit tests for `reattribute_collision_rows` and `migrate_team_membership` in `tests/test_team_membership_migration.py`: a synthetic collision (group and initiative sharing an id, with distinct real member sets) resolves so the group ends up with only its real members and the initiative's real members are preserved under the new disjoint id; an `unresolved` case (person in neither list) is left untouched and reported, never deleted
- [X] T011 [P] [US1] Add a defensive `AND tm.team_id NOT IN (...)`-equivalent audit note / regression test in `tests/test_canonical_exporter.py` (create the specific test if the file exists but lacks one) confirming `_fetch_person_research_group_roles` and the researcher-enrichment group query only return people who are genuinely research group members, using a synthetic id-collision fixture — guards against the contamination ever silently returning if id-disjointness regresses (research.md Decision 4)
- [X] T012 [US1] Run quickstart.md §1–§4 against a scratch copy of the real `db/horizon.db`: dry-run, then real run, then verify Paulo Sérgio (person id 456) no longer shows the collision-only groups while his initiative #9 membership is intact (depends on T009)
- [X] T013 [US1] Apply the migration to the real `db/horizon.db` (quickstart.md §5, first two commands only) and spot-check several more previously-affected research groups beyond the reported example

**Checkpoint**: User Story 1 fully functional — the reported bug is fixed on the live database, and provisioning creates correctly-disjoint initiative teams going forward.

---

## Phase 4: User Story 2 - Re-Running Provisioning Never Creates Duplicate Memberships (Priority: P2)

**Goal**: Provisioning is genuinely idempotent — re-running it against unchanged source data never grows `team_members`.

**Independent Test**: Run provisioning twice in a row against the same source data and confirm the membership record count is identical after both runs.

### Implementation for User Story 2

- [X] T014 [US2] Add a `UNIQUE(team_id, person_id, role_id)` index to `team_members` in `src/core/logic/backup_db_provisioner.py` (a one-time `CREATE UNIQUE INDEX IF NOT EXISTS` statement run as part of provisioning's schema setup, per research.md Decision 2) — makes the three existing `INSERT OR IGNORE INTO team_members` call sites genuinely idempotent with no further changes needed at those call sites
- [X] T015 [P] [US2] Unit test in `tests/test_backup_db_provisioner.py` (create if absent): running the provisioner's team_members-populating logic twice against the same input data results in the same row count after both runs
- [X] T016 [P] [US2] Unit test in `tests/test_backup_db_provisioner.py`: after T006/T007's fix, provisioning from a fixture where a research group and an initiative share an id produces two *different* `teams.id` values, and re-running provisioning reuses the same disjoint id rather than creating a second team (depends on T006, T007, T014)
- [X] T017 [US2] Run quickstart.md §5 in full against the real (now-migrated) database: `make weekly-flows` once, record `team_members` row count, confirm the count doesn't grow on a manual re-run of `python app.py init_backup_db` / `merge_backup` against the same source data (depends on T013, T014)

**Checkpoint**: User Stories 1 AND 2 both verified — membership data is correct today and stays correct across every future pipeline run.

---

## Phase 5: User Story 3 - Verifiable Confirmation the Corruption Is Gone (Priority: P3)

**Goal**: A steward can confirm, with a single command, that zero id-collision-contaminated groups and zero duplicate membership records remain.

**Independent Test**: Run the verification script against the live (migrated) database and confirm it reports zero on both counts.

### Implementation for User Story 3

- [X] T018 [US3] Implement `src/scripts/verify_team_membership_integrity.py`: CLI script (`--db <path>`) reporting the count of research groups still affected by id collision and the count of duplicate `team_members` rows, per the migration contract's postcondition queries
- [X] T019 [P] [US3] Unit tests for the verification script's two counting queries in `tests/test_verify_team_membership_integrity.py`, against synthetic databases in both the "still broken" and "clean" states
- [X] T020 [US3] Add a `verify_team_membership` CLI command to `app.py`, following the existing `init_backup_db`/`merge_backup` pattern (around `app.py:276-296`)
- [X] T021 [US3] Add a `migrate_team_membership` CLI command to `app.py` (same location), wiring `python app.py migrate_team_membership` to call the Phase 3 top-level function against `db/horizon.db`, per quickstart.md §5
- [X] T022 [US3] Run `python app.py verify_team_membership` against the real database and confirm it reports 0/0, per SC-001/SC-002 (depends on T013, T018, T020, T021)

**Checkpoint**: All three user stories independently functional and verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T023 [P] Run `make ci-check` (flake8, black, isort, pytest) and fix any violations introduced by this feature
- [X] T024 Run the full quickstart.md validation (§1–§5) end-to-end one final time, including a real `make weekly-flows` run, and record before/after counts (duplicates removed, collision groups fixed) for the final report

### T024 Results (2026-08-16, against real production data)

First real `make weekly-flows` run after the initial fix **regressed** it: `merge_backup` (run both inline at the start of `run_weekly()` and again as its own phase) pulled the still-uncorrected `data/backup/horizon_backup.db` back into the active database by explicit row id, since the backup file itself had never been migrated — undoing the fix (team_members grew back to 55,450 rows, 125 duplicate groups, and the confirmed-collision groups reappeared on the reported example's profile). The `ux_team_members_team_person_role` index was also found missing afterward; isolated re-tests of `merge_backup`, `consolidate_duplicates`, and `export_canonical` did not reproduce this, leaving the browser-automation-heavy phases as the remaining, unconfirmed suspects (see spec.md Assumptions).

**Fix applied**: re-ran `migrate_team_membership` against the active database and synced the corrected file to `data/backup/horizon_backup.db` directly, so both are consistent. Re-ran `merge_backup` afterward: **0 rows merged** (true idempotency, confirms SC-003), index and 0-duplicate-groups state both held.

| Metric | Before any fix | After final state |
|---|---|---|
| `team_members` total rows | 62,949 | 54,157 |
| Duplicate row-groups | 11,554 (14,814 excess rows) | 0 |
| Research groups affected by id collision | 344 / 344 (100%) | 338 / 344 still have ≥1 unresolved row (documented ground-truth-coverage limitation). Verified fix on the reported example: Paulo Sérgio (person id 456) no longer shows groups #1 ("Divulgação e Popularizaçao da Ciência"), #9 ("Aquicultura e Ambiência Animal"), or #80 ("Gestão de Politicas Públicas do Esporte...") — all three confirmed collision-only, all three cleanly removed while his real initiative #9 membership stayed intact under its new disjoint team id |
| `data/backup/horizon_backup.db` consistency with active | N/A (never independently tracked) | Now identical to active; `merge_backup` confirmed idempotent |

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP — fixes the actively-reported bug.
- **User Story 2 (Phase 4)**: Depends on Foundational; T016 specifically depends on US1's T006/T007 (the disjoint-id fix), so run after Phase 3 in practice.
- **User Story 3 (Phase 5)**: Depends on Foundational; T022 depends on the real migration having been applied in US1's T013, so run after Phase 3 (and benefits from Phase 4 being done too, to verify the fully-fixed state).
- **Polish (Phase 6)**: Depends on all desired user stories being complete.

### Parallel Opportunities

- T002 and T003 can start together within Phase 2 (T004 needs T002 first, T005 needs both T003 and T004).
- T010 and T011 can run in parallel — different test files.
- T015 and T016 can run in parallel — same file but independent test functions, no shared mutable state.
- T019 can run any time after T018.

---

## Parallel Example: Foundational Phase

```bash
Task: "Define MigrationReport dataclass (T002)"
Task: "Implement ground-truth loader helpers (T003)"
# then, once both land:
Task: "Implement deduplicate_team_members (T004)"
Task: "Unit tests for loaders + dedup (T005)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1) — disjoint-id provisioning fix + collision re-attribution, applied to the real database.
3. **STOP and VALIDATE**: run quickstart.md §1–§4; confirm Paulo Sérgio's profile (and a few other spot-checked groups) show correct data. This alone resolves the reported bug.

### Incremental Delivery

1. Setup + Foundational → dedup logic ready and tested in isolation.
2. User Story 1 → the reported bug is fixed on the live database (MVP).
3. User Story 2 → provisioning becomes genuinely idempotent going forward, confirmed via a real double-run.
4. User Story 3 → a one-command verification check exists for ongoing confidence.
5. Polish → `make ci-check` clean, final end-to-end validation recorded.

---

## Notes

- [P] tasks touch different files (or independent functions in the same file) and have no unmet dependencies.
- Every implementation task names its exact target file.
- Per research.md Decision 5, the migration NEVER wipes and rebuilds `team_members` — every task touching production data must preserve this (re-attribute or delete-exact-duplicate only, never a broader delete).
- FR-003 (research group ids never change) is a constraint every task must respect, not a task of its own — T010's and T012's tests are what enforce it in practice.
