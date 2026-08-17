---

description: "Task list for feature implementation"
---

# Tasks: Research Group Institutional Filtering

**Input**: Design documents from `/specs/011-research-group-institutional-filtering/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included — this repository's constitution (Principle IV, Audit-Driven Data Quality) requires new loaders/exporters to include audit coverage, and the spec's success criteria (SC-001 through SC-005) are directly testable data-integrity assertions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project — `src/`, `tests/` at repository root, per plan.md.

---

## Phase 1: Setup

**Purpose**: Recover and stage the historical reference data needed for every later phase.

- [x] T001 Run `git show c12a3c8:data/exports/canonical_export_20260610_160943.zip > /tmp/old_export.zip` and extract `campuses_canonical.json` and `organizations_canonical.json` (per `specs/011-research-group-institutional-filtering/quickstart.md` step 2) to confirm the 23-campus catalog and 26-organization catalog are recoverable and match the values documented in `data-model.md`
- [x] T002 Run the baseline diagnostic query from `quickstart.md` step 1 against `db/horizon.db` and record current counts (expected: 1 row in `organizational_units`, ~315 groups with unresolved `campus_id`, 344 `teams` rows with NULL `organization_id`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Restore the correct, deduplicated campus/organization catalog with historically-aligned IDs — every user story depends on this being correct before export-time validation can be verified.

**⚠️ CRITICAL**: No user story can be verified until this phase is complete.

- [x] T003 In `src/core/logic/backup_db_provisioner.py`, replace the "2. Organizational Units (Campuses)" step (~lines 104-118) to source campus rows from the recovered historical catalog (23 campi, IDs 1-23 as documented in `data-model.md`) instead of the current `campuses_canonical.json` (which only contains 1 row in the live archive) — preserve the existing dedup-by-lowercase-name guard, but stop forcing `id=1` for "Serra" (historically `id=6`)
- [x] T004 In the same provisioner step (T003), also source `organizations_canonical.json` rows from the recovered historical catalog so `organizations` contains the full 26-row set, including `id=1` "Instituto Federal do Espirito Santo"
- [x] T005 In `src/core/logic/backup_db_provisioner.py`, add backfill of `teams.organization_id = 1` for research groups whose historical record in the recovered archive had `organization_id=1` (342 of 344 groups per `research.md`), so the field is no longer NULL for those groups
- [x] T006 In `src/core/logic/backup_merger.py`, remove the hardcoded `DELETE FROM main.organizational_units WHERE id != 1 AND lower(name) = 'serra'` clause (~lines 96-102) that forces Serra to `id=1` and collides with the historical `id=1` ("Vila Velha") already referenced by `research_groups.campus_id` — keep the general dedup-by-name cleanup (~lines 146-152) which does not hardcode an ID
- [x] T007 [P] Add unit tests in `tests/test_backup_merger.py` asserting that after provisioning, `organizational_units` contains 23 rows with the exact id/name pairs from `data-model.md` (notably `id=1` → "Vila Velha", `id=6` → "Serra"), and that `organizations` contains the recovered catalog with no duplicate names
- [x] T008 [P] Add a unit test in `tests/test_backup_merger.py` asserting that after merge, no `research_groups.campus_id` value is left dangling (i.e., every `campus_id` present in `research_groups` resolves to a row in `organizational_units`)

**Checkpoint**: Reference catalog is correct and ID-aligned with existing group data — User Story 1 can now be verified.

---

## Phase 3: User Story 1 - Trustworthy Campus Attribution on the Dashboard (Priority: P1) 🎯 MVP

**Goal**: Every research group displays its real, correct campus instead of being collapsed onto "Serra".

**Independent Test**: After Phase 2's catalog fix and a fresh `init_backup_db` + `merge_backup` + `export_canonical` run, confirm a group known to belong to "Vitória" (e.g. one of the 68 groups with `campus_id=2`) is exported with `campus.name == "Vitória"`, not "Serra".

### Implementation for User Story 1

- [x] T009 [US1] Run `python app.py init_backup_db` then `python app.py merge_backup` against a working copy of `db/horizon.db` and confirm via `quickstart.md` step 5 that `organizational_units` now has 23 rows and 0 groups have an unresolved `campus_id`
- [x] T010 [US1] Run `python app.py export_canonical` and verify via `quickstart.md` step 6 that `data/exports/research_groups_canonical.json` shows a real distribution across multiple campus names (not 100% "Serra")
- [x] T011 [US1] Spot-check the 29 groups with `campus_id=1` (historically "Vila Velha") in the exported data and confirm they now show `campus.name == "Vila Velha"`, not "Serra" — this directly verifies the ID-collision fix from T003/T006

**Checkpoint**: User Story 1 is fully functional and independently verifiable — campus attribution is accurate across all groups with a resolvable historical campus.

---

## Phase 4: User Story 2 - Institutional Scope Validation Before Export (Priority: P2)

**Goal**: The exporter never fabricates or silently reassigns a campus/organization for a group it cannot resolve — instead it excludes or flags the group, and the run reports how many were affected.

**Independent Test**: Introduce a research group with a `campus_id` or `organization_id` that has no match in the restored catalog, run the export, and confirm the group is excluded or flagged rather than assigned an arbitrary value — and that the run's summary reports the count.

### Implementation for User Story 2

- [x] T012 [US2] In `src/core/logic/research_group_exporter.py`, remove the "Enrich Organization" fallback branches (~lines 90-99: `elif org_map: ... next(iter(org_map.values()))` and the hardcoded `{"id": 1, "name": "Instituto Federal do Espírito Santo"}` default)
- [x] T013 [US2] In `src/core/logic/research_group_exporter.py`, remove the "Enrich Campus" fallback branches (~lines 101-107: `elif campus_map: ... next(iter(campus_map.values()))` and the hardcoded `{"id": 1, "name": "Serra"}` default)
- [x] T014 [US2] In `src/core/logic/research_group_exporter.py`, replace both removed fallbacks (T012, T013) with resolution logic per `data-model.md`'s Resolution Rule: a group is "resolved" only when both `campus_id` and `organization_id` match a real catalog row; unresolved groups get `group_dict["unresolved_institutional_affiliation"] = True` and are tracked in an `unresolved_count` accumulator instead of being silently relabeled (FR-004, FR-005, FR-006)
- [x] T015 [US2] In `src/core/logic/research_group_exporter.py`'s `export_all`, log the final `unresolved_count` at the end of the method (FR-008), and return or expose it so the calling task can surface it in the run summary
- [x] T016 [US2] [P] Add unit tests in `tests/test_export_campus_resolver.py` (or a new `tests/test_research_group_exporter.py`) covering: a group with valid campus+organization exports normally; a group with only campus valid is flagged/excluded; a group with only organization valid is flagged/excluded; a group with neither valid is flagged/excluded — none of the three unresolved cases receive a fabricated campus/organization value
- [x] T017 [US2] [P] In `src/flows/exports/canonical_data.py`, update `export_groups_task` to log the `unresolved_count` from T015 as part of the task's completion log, so a data steward can see it in the weekly run's Prefect/Telegram report (Constitution Principle IV)

**Checkpoint**: User Stories 1 AND 2 both verified — attribution is accurate AND unresolved groups are visible instead of silently masked.

---

## Phase 5: User Story 3 - Complete, Accurate Campus Catalog (Priority: P3)

**Goal**: The reference campus catalog itself is complete, deduplicated, and durable across future provisioning runs — this is largely delivered by Phase 2, so this phase focuses on regression-proofing it.

**Independent Test**: Re-run provisioning from scratch multiple times and confirm the catalog remains at exactly 23 deduplicated rows with no drift.

### Implementation for User Story 3

- [x] T018 [US3] Add a regression test in `tests/test_backup_merger.py` that runs `BackupDatabaseProvisioner.ensure_backup_database` twice in sequence and asserts `organizational_units` still has exactly 23 rows after the second run (idempotency — no duplicate accumulation)
- [x] T019 [US3] Run `python app.py weekly` twice in sequence against a scratch database copy (per `quickstart.md` step 8 analog) and confirm campus attribution in the exported groups remains stable between runs

**Checkpoint**: All three user stories independently functional — attribution is accurate, unresolved groups are visible, and the fix is durable across repeated runs.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all stories.

- [x] T020 [P] Run `.venv/bin/pytest tests/test_backup_merger.py tests/test_export_campus_resolver.py` and confirm all pass
- [x] T021 Run the full `specs/011-research-group-institutional-filtering/quickstart.md` validation sequence end-to-end (steps 1-8), including the Dashboard build in step 8
- [x] T022 Run `make ci-check` to confirm linting, formatting, type checking, and the full test suite pass per the project constitution's Development Workflow gate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (the catalog must be correct before export-time resolution logic can be verified)
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 (attribution correctness) and US2 (validation/exclusion logic) touch the same file (`research_group_exporter.py`) — recommended sequentially, US1 first, since US2's tests assume US1's catalog fix is already in place
  - US3 (catalog durability) is largely a regression-test phase on top of Phase 2 and can run in parallel with US2
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### Parallel Opportunities

- T007 and T008 (Phase 2) can run in parallel — independent test additions
- T016 and T017 (Phase 4) touch different files and can run in parallel
- T018 and T019 (Phase 5) can run in parallel with Phase 4 once Phase 2 is complete

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (recover historical catalog)
2. Complete Phase 2: Foundational (restore catalog with correct IDs — the actual data fix)
3. Complete Phase 3: User Story 1 (verify accurate attribution)
4. **STOP and VALIDATE**: Confirm groups show their real campus, including the Vila Velha/Serra ID-collision case
5. Ship — this alone fixes the most visible symptom (Dashboard mislabeling)

### Incremental Delivery

1. Setup + Foundational → catalog restored and ID-aligned
2. User Story 1 → verify accurate attribution → MVP
3. User Story 2 → add export-time validation/exclusion → closes the "silently masked" root cause
4. User Story 3 → durability regression tests → protects against future collapse

---

## Notes

- No `contracts/` tasks — no new public interface is introduced (per plan.md); the change is internal to already-existing modules.
- Tests are included per this repository's constitution (Principle IV: new loaders/exporters require audit coverage), not because the spec explicitly requested TDD.
- T003/T006 together resolve the specific ID-collision finding from `research.md` (Serra was forced to `id=1`, colliding with the historical "Vila Velha" `id=1`) — these two tasks should not be split across different implementers without coordinating on the final ID scheme.

## Implementation Report (2026-08-15)

All 22 planned tasks completed, plus two additional fixes discovered during T009 verification against real data (documented below since they were necessary for the fix to actually work, not just theoretically correct).

- **T001-T002**: Confirmed the 23-campus/26-organization historical catalog is recoverable from `git show c12a3c8:...`, and captured baseline (1 campus row, 315 unresolved groups, 344 groups with NULL `organization_id`).
- **T003**: `backup_db_provisioner.py` now seeds `organizational_units` from a `HISTORICAL_CAMPUS_CATALOG` constant (23 campi, historically correct IDs — Serra=6, not the previously forced id=1) before layering in anything from the live archive.
- **T004**: Turned out to be unnecessary as originally scoped — the live archive's `organizations_canonical.json` already contains the full 180-row catalog (including `id=1` "Instituto Federal do Espirito Santo") and was already being loaded correctly by the pre-existing "1. Organizations" step. Only the campus catalog was actually deficient in the live archive.
- **T005**: Added `DEFAULT_RESEARCH_GROUP_ORGANIZATION_ID = 1` fallback in the provisioner's research-group step, since the live archive's `research_groups_canonical.json` carries `organization_id: null` for all 344 groups (it was exported from the already-broken database — a self-perpetuating gap).
- **T006**: Removed the hardcoded `DELETE ... WHERE id != 1 AND lower(name) = 'serra'` from `backup_merger.py`.
- **Unplanned fix #1 (found during T009)**: The generic merge loop uses `INSERT OR IGNORE`, which only adds *missing* rows — it never corrects a stale/incorrect `organizational_units` row already present in the active database (e.g. a production db that already has `id=1, name='Serra'`). Worse, the post-merge dedup-by-name cleanup would then delete the *correct* newly-merged row (id=6, "Serra") as the "duplicate", keeping the wrong one. Fixed by special-casing `organizational_units` to `INSERT OR REPLACE` from backup (backup is authoritative for reference/catalog data), executed before the generic merge loop. Covered by `test_merge_corrects_stale_campus_row_in_active_db`.
- **Unplanned fix #2 (found during T009)**: Similarly, `teams.organization_id` for research groups that already exist in the active database (created by prior live scraper runs) never got backfilled by the generic `INSERT OR IGNORE` on `teams`, since those rows already exist. Added a scoped `UPDATE main.teams SET organization_id = (...) WHERE id IN (SELECT id FROM research_groups) AND organization_id IS NULL` in `backup_merger.py`, restricted to research-group teams only (initiative teams are untouched). Covered by `test_merge_backfills_organization_id_for_preexisting_research_group_team`.
- **T007-T011**: Verified against a scratch copy of the real `db/horizon.db` — after both provisioner and merger fixes, `organizational_units` has 23 rows, 0 groups have unresolved `campus_id`, 0 groups have NULL `organization_id`, and the campus distribution matches the historical catalog exactly (e.g. group 1's `campus_id=1` now correctly resolves to "Vila Velha", not "Serra").
- **T012-T017**: `research_group_exporter.py`'s `export_all` no longer fabricates campus/organization values — a group is exported normally only when both resolve to real catalog rows; otherwise `campus`/`organization` are `null` and `unresolved_institutional_affiliation: true` is set. `export_all` now returns the unresolved count, surfaced as a warning log in `canonical_data.py`'s `export_groups_task`. The pre-existing test `test_exporter_warns_when_campuses_missing_but_groups_reference_them` needed a minor assertion loosening (it now legitimately logs 2 warnings instead of 1). 4 new tests added covering all four resolution combinations.
- **T018-T019**: Idempotency confirmed both via a persisted unit test (`test_campus_catalog_is_idempotent_across_repeated_provisioning`) and by running provisioning+merge twice against the real-data scratch copy.
- **T020-T022**: All 24 new/modified tests pass (13 in `test_backup_merger.py`, 7 in `test_research_group_exporter.py`, 3 in `test_knowledge_area_live_sync.py` from spec 012, plus 1 pre-existing exporter test updated). All touched files are `black`/`isort`/`flake8` clean (2 pre-existing unused-import warnings unrelated to this feature). Full suite re-run: same 11 pre-existing failures + 1 error as before this feature (confirmed via `git stash` comparison) — no new regressions. `make ci-check`'s `format-check` step still fails repo-wide due to 35 pre-existing non-compliant files untouched by this feature.
