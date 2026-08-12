# Tasks: ZIP Fallback and Multi-Attempt Data Resilience

**Input**: Design documents from `/specs/007-zip-fallback-resilience/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/flow_contract.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test suite setup and mock environment for fallback testing

- [x] T001 Create test file structure in `tests/test_zip_fallback.py`
- [x] T002 Configure test fixtures for mock raw and export directory states in `tests/test_zip_fallback.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core validation helpers for non-blocking ZIP checks and fallback directory scanning

- [x] T003 Implement non-blocking warning logger helper in `scripts/export_zip.py`
- [x] T004 Implement cached JSON extraction validator helper in `src/adapters/sources/sigpesq/adapter.py`

---

## Phase 3: User Story 1 - Graceful Fallback on External Portal Failures (Priority: P1) 🎯 MVP

**Goal**: Ensure pipeline reuses cached raw files and extracted project JSONs when SigPesq or another external portal is unreachable.

**Independent Test**: Simulate SigPesq network failure with pre-existing `data/exports/project_sigpesq_files_json/*.json` and verify pipeline continues to completion.

### Implementation for User Story 1

- [x] T005 [P] [US1] Update `SigPesqAdapter.extract` in `src/adapters/sources/sigpesq/adapter.py` to check for cached project JSONs in `data/exports/project_sigpesq_files_json/` before failing on network errors.
- [x] T006 [US1] Add fallback warning logging when live portal download fails but cached extractions are present in `src/adapters/sources/sigpesq/adapter.py`.
- [x] T007 [P] [US1] Write unit tests for `SigPesqAdapter` fallback in `tests/test_zip_fallback.py`.

**Checkpoint**: User Story 1 functional - external source offline events safely fall back to cached local files without raising unhandled exceptions.

---

## Phase 4: User Story 2 - Guaranteed ZIP Archive Creation (Priority: P1)

**Goal**: Guarantee that `exports_canonical.zip` and timestamped ZIPs are generated without deletion even when optional subgraph folders are empty or produce non-critical validation warnings.

**Independent Test**: Run `scripts/export_zip.py data/exports` with empty graph subdirectories and verify ZIP file is retained and valid.

### Implementation for User Story 2

- [x] T008 [P] [US2] Modify `_validate_zip()` in `scripts/export_zip.py` to log non-fatal warnings for missing optional subgraphs instead of unlinking `archive_path`.
- [x] T009 [P] [US2] Update `zip_exports_task` in `src/flows/exports/canonical_data.py` to ignore files matching `*.zip` during directory traversal.
- [x] T010 [US2] Add CLI flag `--clean-loose` support to `scripts/export_zip.py` to allow selective cleanup of loose JSONs in production runs while preserving loose JSONs in dev.
- [x] T011 [P] [US2] Write unit tests for `_validate_zip()` non-destructive behavior in `tests/test_zip_fallback.py`.
- [x] T012 [P] [US2] Write unit tests for `zip_exports_task` traversal in `tests/test_zip_fallback.py`.

**Checkpoint**: User Story 2 functional - ZIP archives are created and preserved across all pipeline execution states.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Formatting, quality gates, and end-to-end verification

- [x] T013 [P] Format and lint code with `black`, `isort`, and `flake8`
- [x] T014 Run full test suite with `pytest tests/test_zip_fallback.py`
- [x] T015 Execute quickstart validation steps from `specs/007-zip-fallback-resilience/quickstart.md`

---

## Dependencies & Execution Order

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2).
- **User Story 2 (P1)**: Can start after Foundational (Phase 2).
- US1 and US2 touch different files (`adapter.py` vs `export_zip.py` / `canonical_data.py`) and can be implemented in parallel.

### Within Each User Story

- T005 before T006
- T008, T009, T010 can run in parallel
- Unit tests can run after implementation

---

## Implementation Strategy

### MVP First (User Story 1 & 2 Core)

1. Complete Setup (T001-T002) and Foundational (T003-T004).
2. Complete US1 (T005-T007) and US2 (T008-T012).
3. Validate `make export-canonical` generates `exports_canonical.zip` reliably.
