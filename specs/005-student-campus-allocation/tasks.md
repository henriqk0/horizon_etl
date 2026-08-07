# Tasks: Student Campus Allocation Hierarchy

**Input**: Design documents from `/specs/005-student-campus-allocation/`  
**Prerequisites**: [`plan.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/plan.md) (required), [`spec.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/spec.md) (required for user stories), [`research.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/research.md), [`data-model.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/data-model.md), [`contracts/`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/contracts/students-canonical-export.json)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent functions)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify contract and feature directory configuration

- [X] T001 [P] Verify feature environment and schema contract in `specs/005-student-campus-allocation/contracts/students-canonical-export.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure in `ExportCampusResolver` that MUST be complete before user stories can be evaluated

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Define internal resolver state & data structures for 3-tier cascade and multi-campus mapping in `src/core/logic/export_campus_resolver.py`
- [X] T003 [P] Add `campus_resolution` audit dictionary helper in `src/core/logic/export_campus_resolver.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Project-Based Campus Allocation (Priority: P1) 🎯 MVP

**Goal**: Allocate student entities to campus based on their participation in research or extension projects (initiatives/editais)

**Independent Test**: Unit test verifying that a student linked to a project with a valid campus resolves to `resolved_via: "project"` and inherits the project's campus.

### Implementation for User Story 1

- [X] T004 [P] [US1] Implement project campus index query (`_load_initiative_campuses`) in `src/core/logic/export_campus_resolver.py`
- [X] T005 [US1] Implement Level 1 project-level campus resolution for student entities in `src/core/logic/export_campus_resolver.py`
- [X] T006 [P] [US1] Write unit test for Level 1 project campus resolution in `tests/test_export_campus_resolver.py`

**Checkpoint**: User Story 1 (MVP) functional and testable independently

---

## Phase 4: User Story 2 - Research Group Fallback Allocation (Priority: P2)

**Goal**: Fall back to Research Group membership campus when no project-level campus is found

**Independent Test**: Unit test verifying that a student with no project campus who belongs to a Research Group inherits the group's campus with `resolved_via: "research_group"`.

### Implementation for User Story 2

- [X] T007 [P] [US2] Implement Level 2 research group fallback resolution in `src/core/logic/export_campus_resolver.py`
- [X] T008 [P] [US2] Write unit test for Level 2 research group fallback resolution in `tests/test_export_campus_resolver.py`

**Checkpoint**: User Stories 1 AND 2 functional independently

---

## Phase 5: User Story 3 - Main Advisor Fallback & Multi-Campus Tie-Breaking (Priority: P3)

**Goal**: Fall back to main academic advisor campus when no project or group campus is found, and support multi-campus allocation for ties

**Independent Test**: Unit test verifying main advisor campus fallback and multi-campus allocation when multiple main advisors belong to different campuses.

### Implementation for User Story 3

- [X] T009 [P] [US3] Implement main advisor query (`_load_advisorship_campuses`) and Level 3 fallback resolution in `src/core/logic/export_campus_resolver.py`
- [X] T010 [US3] Implement multi-campus aggregation and deterministic tie-breaker for single `campus` field in `src/core/logic/export_campus_resolver.py`
- [X] T011 [P] [US3] Update canonical student export payload enrichment (`campus`, `campuses`, `campus_resolution`) in `src/core/logic/canonical_exporter.py`
- [X] T012 [P] [US3] Write unit test for main advisor fallback and multi-campus tie-breaking in `tests/test_export_campus_resolver.py`
- [X] T013 [P] [US3] Write integration test for enriched `students_canonical.json` export in `tests/test_canonical_exporter.py`

**Checkpoint**: All 3 user stories functional and multi-campus exports fully validated

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and quality gates

- [X] T014 [P] Execute quickstart validation scenarios in `specs/005-student-campus-allocation/quickstart.md`
- [X] T015 [P] Run full CI quality check suite (`make ci-check`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase
- **User Story 2 (Phase 4)**: Depends on Foundational phase
- **User Story 3 (Phase 5)**: Depends on Foundational phase & US1/US2 resolver hooks
- **Polish (Phase 6)**: Depends on all user stories complete

### Parallel Opportunities

- Tasks marked `[P]` inside the same phase can be executed concurrently.
- `T006` [US1], `T008` [US2], and `T012` [US3] tests can be written in parallel once internal resolver interfaces are defined.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1 - Project Campus Allocation).
3. Validate US1 independently with `pytest tests/test_export_campus_resolver.py -k "test_student_campus_project"`.

### Full Incremental Delivery

1. Complete Phase 1 & Phase 2.
2. Deliver US1 (Projects) $\rightarrow$ Deliver US2 (Research Groups) $\rightarrow$ Deliver US3 (Main Advisors & Multi-Campus).
3. Run `quickstart.md` scenarios and `make ci-check`.
