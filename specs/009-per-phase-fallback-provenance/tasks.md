# Tasks: Per-Phase ZIP Fallback Seeding & Data Provenance Reporting

**Input**: Design documents from `/specs/009-per-phase-fallback-provenance/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/flow_contract.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test suite setup and mock environment for provenance and database seeding tests

- [x] T001 Create test file structure in `tests/test_provenance_and_seeder.py`
- [x] T002 Configure test fixtures for mock canonical export JSONs and SQLite database in `tests/test_provenance_and_seeder.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core logic helpers for reading/writing phase provenance and database seeding

- [x] T003 Implement `ProvenanceTracker` helper in `src/core/logic/provenance_tracker.py` to write/read origin marker files
- [x] T004 Implement `CanonicalDatabaseSeeder` in `src/core/logic/canonical_database_seeder.py` to seed `research_groups` table from `data/exports/research_groups_canonical.json`

---

## Phase 3: User Story 1 - Transparent Provenance in Final Summary Table (Priority: P1) 🎯 MVP

**Goal**: Record and render data provenance tags (`[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, `[VAZIO]`) alongside every executed pipeline phase in the CLI summary table and Telegram completion notifications.

**Independent Test**: Run pipeline where steps record provenance markers, and verify `weekly_orchestrator` prints origin tags alongside step names in the summary table.

### Implementation for User Story 1

- [x] T005 [P] [US1] Update `SigPesqAdapter` in `src/adapters/sources/sigpesq/adapter.py` to set provenance marker to `ZIP ANTERIOR` on fallback execution
- [x] T006 [US1] Update `_run_phase()` and summary printing in `src/flows/pipelines/weekly_orchestrator.py` to read provenance markers and render tags (`[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, `[VAZIO]`)
- [x] T007 [P] [US1] Update Telegram message formatter `_notify()` in `src/flows/pipelines/weekly_orchestrator.py` to include step provenance tags
- [x] T008 [P] [US1] Write unit tests for `ProvenanceTracker` and orchestrator tag rendering in `tests/test_provenance_and_seeder.py`

**Checkpoint**: User Story 1 functional - origin tags are displayed transparently in summary table and notifications.

---

## Phase 4: User Story 2 - Per-Phase Database Seeding on Source Unavailability (Priority: P2)

**Goal**: Automatically seed database tables from canonical JSON artifacts when live ingestion sources fail or return zero items, ensuring downstream steps (such as CNPq group sync) execute with full database context.

**Independent Test**: Clear `research_groups` table in database with `research_groups_canonical.json` present in `data/exports/`, run `get_groups_to_sync()`, and verify database is seeded and group URLs are returned for processing.

### Implementation for User Story 2

- [x] T009 [P] [US2] Update `get_groups_to_sync()` in `src/flows/cnpq/groups.py` to invoke `CanonicalDatabaseSeeder().seed_research_groups_if_empty()` before querying database
- [x] T010 [P] [US2] Write unit tests for `CanonicalDatabaseSeeder` seeding `horizon.db` and triggering `cnpq_sync` in `tests/test_provenance_and_seeder.py`

**Checkpoint**: User Story 2 functional - empty database tables are populated automatically from prior canonical export artifacts.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Formatting, quality gates, and end-to-end verification

- [x] T011 [P] Format and lint code with `black`, `isort`, and `flake8`
- [x] T012 Run full test suite with `pytest tests/test_provenance_and_seeder.py`
- [x] T013 Execute quickstart verification steps from `specs/009-per-phase-fallback-provenance/quickstart.md`

---

## Dependencies & Execution Order

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2).
- **User Story 2 (P2)**: Can start after Foundational (Phase 2).

### Within Each User Story

- T003 & T004 before T005, T006, T009
- T005 & T009 can run in parallel
- Unit tests can run after implementation

---

## Implementation Strategy

### MVP First (User Story 1 Core)

1. Complete Setup (T001-T002) and Foundational (T003-T004).
2. Complete US1 (T005-T008).
3. Validate `weekly_orchestrator` prints origin tags (`[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, `[VAZIO]`).
