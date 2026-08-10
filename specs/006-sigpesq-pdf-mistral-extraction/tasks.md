# Tasks: SigPesq PDF Download & Mistral Report Extraction

**Input**: Design documents from `/specs/006-sigpesq-pdf-mistral-extraction/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initial folder creation and environment setup

- [x] T001 Create raw PDF download folder `data/raw/sigpesq/projects/` and export JSON folder `data/exports/project_sigpesq_files_json/`
- [x] T002 Verify environment variable validation (`SIGPESQ_USERNAME`, `SIGPESQ_PASSWORD`, `MISTRAL_KEY`) in `src/adapters/sources/sigpesq/adapter.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Base infrastructure required before user stories

- [x] T003 [P] Create test module structure in `tests/test_sigpesq_project_extraction.py`
- [x] T004 [P] Update export path defaults and constants in `src/flows/sigpesq/enrich_projects.py`

---

## Phase 3: User Story 1 - Automate Download of Project PDF Reports (Priority: P1) 🎯 MVP

**Goal**: Download research project PDF report files from the SigPesq portal into `data/raw/sigpesq/projects/`.

**Independent Test**: Execute project PDF download with test credentials and verify `.pdf` files matching project codes appear in `data/raw/sigpesq/projects/`.

### Implementation for User Story 1

- [x] T005 [US1] Add `ProjectFilesDownloadStrategy` download method in `src/adapters/sources/sigpesq/adapter.py`
- [x] T006 [US1] Implement HTTP 429 rate-limiting retry backoff and skip-existing file logic for project downloads in `src/adapters/sources/sigpesq/adapter.py`
- [x] T007 [P] [US1] Add unit tests for project PDF download orchestration in `tests/test_sigpesq_project_extraction.py`

**Checkpoint**: User Story 1 complete — PDFs can be downloaded independently.

---

## Phase 4: User Story 2 - Extract Structured Project Data Using Mistral AI (Priority: P2)

**Goal**: Process project PDFs using Mistral AI (text extraction & OCR fallback) into validated JSON reports under `data/exports/project_sigpesq_files_json/`.

**Independent Test**: Run extraction component on a sample project PDF and verify structured JSON output in `data/exports/project_sigpesq_files_json/`.

### Implementation for User Story 2

- [x] T008 [P] [US2] Implement Mistral extraction wrapper `SigPesqProjectExtractor` in `src/adapters/sources/sigpesq/mistral_extractor.py`
- [x] T009 [US2] Implement synchronous PDF extraction (`ProjectExtractor`) with automatic OCR fallback (`mistral-ocr-latest`) in `src/adapters/sources/sigpesq/mistral_extractor.py`
- [x] T010 [US2] Implement batch extraction (`BatchProjectExtractor`) with configurable `use_batch` flag in `src/adapters/sources/sigpesq/mistral_extractor.py`
- [x] T011 [US2] Implement LGPD PII masking for CPF fields in extracted team members before writing JSON artifacts in `src/adapters/sources/sigpesq/mistral_extractor.py`
- [x] T012 [P] [US2] Add unit tests for Mistral extraction and OCR fallback in `tests/test_sigpesq_project_extraction.py`

**Checkpoint**: User Story 2 complete — PDFs can be converted to structured JSON files independently.

---

## Phase 5: User Story 3 - Integrate Project Extraction with Enrichment Pipeline (Priority: P3)

**Goal**: Orchestrate PDF download, Mistral extraction, and database enrichment via a Prefect flow.

**Independent Test**: Run `extract_projects_flow` and verify research project initiatives in the database are updated.

### Implementation for User Story 3

- [x] T013 [US3] Create Prefect flow `extract_projects_flow` registered with `telegram_flow_state_handlers()` in `src/flows/sigpesq/extract_projects.py`
- [x] T014 [US3] Connect `extract_projects_flow` to delegate to `enrich_projects_flow` upon successful extraction in `src/flows/sigpesq/extract_projects.py`
- [x] T015 [P] [US3] Add Makefile target `etl-sigpesq-projects` for end-to-end flow execution in `Makefile`
- [x] T016 [P] [US3] Add end-to-end integration test for full extraction and enrichment pipeline in `tests/test_sigpesq_project_extraction.py`

**Checkpoint**: User Story 3 complete — full pipeline operates seamlessly.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Code quality, formatting, and quickstart validation

- [x] T017 [P] Run linting, formatting, and type checks (`make ci-check`) across all modified files
- [x] T018 Run quickstart validation per `specs/006-sigpesq-pdf-mistral-extraction/quickstart.md`

---

## Dependencies & Execution Order

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 Foundational tasks.
- **User Story 2 (P2)**: Can start after Phase 2 Foundational tasks (consumes PDFs from US1).
- **User Story 3 (P3)**: Can start after US1 and US2 (orchestrates both).

### Parallel Opportunities

- `T003` and `T004` (Foundational) can run in parallel.
- `T008` (`mistral_extractor.py` wrapper) can be developed in parallel with US1 download logic (`T005`).
- `T012` (Extraction unit tests) and `T015` (Makefile target) can run in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Setup (Phase 1) + Foundational (Phase 2).
2. Download PDFs (US1).
3. Extract JSONs via Mistral AI (US2).
4. Run existing `enrich_projects_flow` to verify database ingestion.
