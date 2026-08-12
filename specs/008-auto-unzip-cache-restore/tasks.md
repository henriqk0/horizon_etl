# Tasks: Automated Export ZIP Extraction & Cache Bootstrapping

**Input**: Design documents from `/specs/008-auto-unzip-cache-restore/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/flow_contract.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test suite setup and mock environment for cache bootstrap testing

- [x] T001 Create test file structure in `tests/test_auto_unzip_bootstrap.py`
- [x] T002 Configure test fixtures for mock export ZIP archives and export directories in `tests/test_auto_unzip_bootstrap.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core logic helper for ZIP archive discovery and extraction

- [x] T003 Implement `ExportCacheBootstrapper.find_latest_archive()` searching `data/exports` and `./` in `src/core/logic/export_cache_bootstrapper.py`
- [x] T004 Implement extraction and retention logic in `ExportCacheBootstrapper.bootstrap()` in `src/core/logic/export_cache_bootstrapper.py`

---

## Phase 3: User Story 1 - Automated Cache Bootstrapping on Pipeline Start (Priority: P1) 🎯 MVP

**Goal**: Automatically discover and extract pre-existing export archives (`canonical_export_*.zip` or `exports_canonical.zip`) on pipeline start, restoring `project_sigpesq_files_json/*.json` reports and canonical manifests without manual intervention.

**Independent Test**: Place a mock ZIP in `data/exports/` or project root `./`, run `ExportCacheBootstrapper().bootstrap()`, and verify contents are extracted to `data/exports/` and source ZIP is retained.

### Implementation for User Story 1

- [x] T005 [P] [US1] Implement `bootstrap_export_cache_task` Prefect wrapper in `src/flows/exports/canonical_data.py`
- [x] T006 [US1] Invoke `bootstrap_export_cache_task` at the start of `run_weekly()` in `src/flows/pipelines/weekly_orchestrator.py`
- [x] T007 [P] [US1] Write unit tests for archive discovery, extraction, and retention in `tests/test_auto_unzip_bootstrap.py`

**Checkpoint**: User Story 1 functional - pipeline automatically unpacks existing export archives at launch.

---

## Phase 4: User Story 2 - Safe Graceful Fallback when No ZIP Exists (Priority: P2)

**Goal**: Ensure clean initial runs in fresh environments log an info message and proceed from scratch without crashing if no ZIP archive is found or if a ZIP is corrupted.

**Independent Test**: Run `ExportCacheBootstrapper().bootstrap()` in an empty directory or with a corrupted ZIP file, verifying that a warning/info log is emitted and `restored: False` is returned cleanly.

### Implementation for User Story 2

- [x] T008 [P] [US2] Add empty folder warning logging and corrupted ZIP exception handling in `src/core/logic/export_cache_bootstrapper.py`
- [x] T009 [P] [US2] Write unit tests for empty directory and corrupted ZIP fallback scenarios in `tests/test_auto_unzip_bootstrap.py`

**Checkpoint**: User Story 2 functional - fresh environments handle missing/corrupted archives gracefully.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Formatting, quality gates, and end-to-end verification

- [x] T010 [P] Format and lint code with `black`, `isort`, and `flake8`
- [x] T011 Run full test suite with `pytest tests/test_auto_unzip_bootstrap.py`
- [x] T012 Execute quickstart verification steps from `specs/008-auto-unzip-cache-restore/quickstart.md`

---

## Dependencies & Execution Order

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2).
- **User Story 2 (P2)**: Can start after Foundational (Phase 2).

### Within Each User Story

- T003 & T004 before T005, T006
- T008 can run in parallel with T005
- Unit tests can run after implementation

---

## Implementation Strategy

### MVP First (User Story 1 Core)

1. Complete Setup (T001-T002) and Foundational (T003-T004).
2. Complete US1 (T005-T007).
3. Validate `ExportCacheBootstrapper().bootstrap()` unpacks root or `data/exports/` ZIP files.
