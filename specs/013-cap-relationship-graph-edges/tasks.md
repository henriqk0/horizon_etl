---

description: "Task list for Cap Relationship Graph Edges"
---

# Tasks: Cap Relationship Graph Edges

**Input**: Design documents from `/specs/013-cap-relationship-graph-edges/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included — the project constitution requires modified generators to have corresponding tests, and this session's established pattern (specs 011/012) always added tests alongside implementation.

**Organization**: Tasks are grouped by user story (US1/US2/US3, per spec.md's priorities) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project — `src/`, `tests/` at repository root (per plan.md's Structure Decision).

---

## Phase 1: Setup

**Purpose**: Create the new shared module's file so Phase 2 has somewhere to add code

- [X] T001 Create empty `src/core/logic/graph_edge_capper.py` with a module docstring describing its purpose (per-node degree capping used by both graph generator families)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared trimming utility that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Define the `EdgeCapResult` dataclass (`graph`, `original_edge_count`, `trimmed_edge_count`, `removed_edge_count`, `reduction_pct`) in `src/core/logic/graph_edge_capper.py`, per data-model.md
- [X] T003 Implement `cap_node_degree(graph, max_edges_per_node=3) -> EdgeCapResult` in `src/core/logic/graph_edge_capper.py`: per-node top-3 ranking by `(weight, neighbor_id)`, union rule across nodes (FR-007), preserves every original node including now-isolated ones (FR-006), returns populated `EdgeCapResult` (depends on T002)
- [X] T004 [P] Unit tests for `cap_node_degree()` in `tests/test_graph_edge_capper.py`: node-count preservation, per-node ≤3-plus-union-extras edge retention, deterministic tie-break on repeated calls (SC-005), correct `EdgeCapResult` stats including the zero-original-edges case (no division by zero)

**Checkpoint**: Foundation ready — `cap_node_degree` is implemented and tested in isolation; user story work can now begin.

---

## Phase 3: User Story 1 - Dashboard Build Succeeds After a Data Sync (Priority: P1) 🎯 MVP

**Goal**: Every relationship and collaboration graph export shrinks enough (via the Phase 2 utility) that the Dashboard's production build completes without an out-of-memory error.

**Independent Test**: Regenerate exports from real canonical JSON (quickstart.md §2), confirm file sizes drop by an order of magnitude, then run the Dashboard's production build (quickstart.md §3) and confirm it completes within the existing memory budget.

### Implementation for User Story 1

- [X] T005 [US1] Call `cap_node_degree` inside `PeopleRelationshipGraphGenerator._serialize_graph_result` in `src/core/logic/people_relationship_graph_generator.py`, replacing the graph passed to `json_graph.node_link_data` and to `_build_graph_stats` with the trimmed graph (covers the full graph and the 4 classification subgraphs — FR-001, FR-002, FR-005)
- [X] T006 [US1] Call `cap_node_degree` inside `_export_research_group_graphs`'s per-group loop in `src/core/logic/people_relationship_graph_generator.py`, before that group's `_serialize_graph_result` call (covers all 344 per-research-group graphs — FR-002) (depends on T005, same file)
- [X] T007 [P] [US1] Call `cap_node_degree` inside `PeopleCollaborationGraphGenerator.generate` in `src/core/logic/people_collaboration_graph_generator.py`, replacing `G` with the trimmed graph before `json_graph.node_link_data` and before computing `graph_stats` (covers the global graph and, via inheritance, all 4 classification-filtered collaboration exports — FR-001, FR-002, FR-005)
- [X] T008 [P] [US1] Extend `tests/test_people_relationship_graph_generator.py` (create if it doesn't exist) with assertions that generated full, classification, and per-group graphs have ≤3-plus-union-extras edges per node and unchanged node counts
- [X] T009 [P] [US1] Extend `tests/test_people_collaboration_graph_generator.py` (create if it doesn't exist) with the same assertions for the collaboration graph family
- [X] T010 [US1] Run quickstart.md §2 (real-data regeneration + size check) and §3 (Dashboard build) end-to-end; confirm SC-001 and SC-002 (depends on T005, T006, T007)

**Checkpoint**: User Story 1 fully functional — Dashboard build succeeds against freshly regenerated exports.

---

## Phase 4: User Story 2 - Exports Stay Practical to Generate and Distribute as the Dataset Grows (Priority: P2)

**Goal**: Confirm the fix is a durable, scale-independent bound, not a one-time patch that regresses as the dataset grows.

**Independent Test**: Generate exports from a dataset containing an unusually large synthetic group/initiative and confirm the resulting file size grows roughly linearly with people count, not quadratically with group/initiative size.

### Implementation for User Story 2

- [X] T011 [P] [US2] Add a regression test in `tests/test_people_relationship_graph_generator.py` using a synthetic research group with 500 members: assert post-cap edge count stays in the same order of magnitude as node count (not O(n²)) (depends on T008, same file)
- [X] T012 [P] [US2] Add the equivalent regression test in `tests/test_people_collaboration_graph_generator.py` using a synthetic 500-member initiative (depends on T009, same file)
- [X] T013 [US2] Re-run quickstart.md §2 after T005–T007 are in place and confirm none of the generated exports (full, classification, or per-group) approach their previously measured problematic sizes (455MB / 215MB / 31MB-per-group) — validates SC-003 (depends on T010)

**Checkpoint**: User Stories 1 AND 2 both verified — the fix holds under growth, not just today's dataset snapshot.

---

## Phase 5: User Story 3 - Graph Statistics Stay Accurate After Trimming (Priority: P3)

**Goal**: Bundled statistics reflect the trimmed graph, and every export reports how much trimming happened (FR-008/SC-006), so the fix's effect is verifiable without opening the files and future regressions are visible in logs.

**Independent Test**: For a trimmed export, recompute node/edge/degree counts directly from its `graph` section and confirm they exactly match `graph_stats`; confirm a trim-summary log line is present when generating exports.

### Implementation for User Story 3

- [X] T014 [US3] Add a `logger.info` trim-summary line (removed edge count, reduction %) in `src/core/logic/people_relationship_graph_generator.py`, at each of the call sites added in T005/T006 (full graph, each classification graph, each per-group graph) (depends on T005, T006, same file)
- [X] T015 [P] [US3] Add a `logger.info` trim-summary line (removed edge count, reduction %) in `src/core/logic/people_collaboration_graph_generator.py`'s `generate`, extending its existing "N nodes, M edges" log line — inherited automatically by all 4 collaboration subclasses (depends on T007, same file)
- [X] T016 [P] [US3] Add a test in `tests/test_people_relationship_graph_generator.py` asserting every `graph_stats` field (node/edge counts, `top_people_by_weighted_degree`, degree values) exactly matches an independent recount performed directly against that same result's `graph` section (depends on T008, same file)
- [X] T017 [P] [US3] Add the equivalent `graph_stats`-matches-recount test in `tests/test_people_collaboration_graph_generator.py` (depends on T009, same file)
- [X] T018 [US3] Run quickstart.md §4 (audit signal check) during a real `make weekly-flows` run and confirm trim-summary log lines are present and correct for the `people_relationship_graph` phase (depends on T014, T015)

**Checkpoint**: All three user stories independently functional — build succeeds, growth is bounded, and the fix's effect is both correct and observable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final quality gate per the project constitution's Development Workflow & Quality Gates

- [X] T019 [P] Run `make ci-check` (flake8, black, isort, mypy, pytest) and fix any violations introduced by this feature
- [X] T020 Run the full quickstart.md validation (§1–§4) end-to-end one final time after all tasks are complete, and record the before/after file sizes and Dashboard build result

### T020 Results (2026-08-16, against real production data)

| Export | Before | After | Reduction |
|---|---|---|---|
| `people_relationship_graph.json` | 455MB | 13MB | ~97% |
| `researchers_only_relationship_graph.json` | 215MB | 6.9MB | ~97% |
| `research_group_relationship_graphs/` (344 files) | 627MB total, up to 31MB/file | 76MB total, up to 1.4MB/file | ~88% total, ~95% worst-case file |
| `researchers_only_collaboration_graph.json` | 2.7MB | 2.3MB | ~15% (never had the clique-explosion problem) |

Generation time: ~152s for the full relationship-graph bundle (full + 4 classification + 344 per-group graphs), well inside the `people_relationship_graph` phase's 1800s budget.

**Dashboard build** (`npm run build`, real `horizon_dashboard_h` checkout, synced with the capped exports above): **29,061 pages built in 326.94s, completed successfully**, using only the project's already-configured 8GB heap (`--max-old-space-size=8192`) — no `JavaScript heap out of memory` crash, no need for the 16GB override previously required to even attempt (and still fail) the build. Confirms SC-001.

Trim-summary log lines (FR-008/SC-006) confirmed present for every export during generation, e.g. `Edge cap: 87954 -> 1730 edges (86224 removed, 98.0% reduction) for scope research_group`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup (needs the file T001 creates). BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only.
- **User Story 2 (Phase 4)**: Depends on Foundational; its tests extend files US1 creates (T008/T009), so run after Phase 3 in practice even though it has no *new* blocking dependency on US1's outcome.
- **User Story 3 (Phase 5)**: Depends on Foundational; its logging/tests extend the same call sites US1 adds (T005–T007), so run after Phase 3.
- **Polish (Phase 6)**: Depends on all desired user stories being complete.

### Parallel Opportunities

- T002 and T004 can start together within Phase 2 once T001 exists (T003 needs T002 first).
- T007 (collaboration generator) can run in parallel with T005/T006 (relationship generator) — different files.
- T008 and T009 can run in parallel — different test files.
- T011 and T012 can run in parallel — different test files.
- T015, T016, T017 can run in parallel with each other (and with T014, different files).
- T019 can start as soon as all implementation tasks are done, in parallel with writing T020's manual validation notes.

---

## Parallel Example: User Story 1

```bash
# After Phase 2 (Foundational) completes:
Task: "Call cap_node_degree in PeopleCollaborationGraphGenerator.generate (T007)"
# ...while, independently:
Task: "Call cap_node_degree in PeopleRelationshipGraphGenerator._serialize_graph_result (T005)"

# Once T005/T006/T007 land, the two test-extension tasks run in parallel:
Task: "Extend tests/test_people_relationship_graph_generator.py (T008)"
Task: "Extend tests/test_people_collaboration_graph_generator.py (T009)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — the shared `cap_node_degree` utility, tested in isolation.
2. Complete Phase 3 (User Story 1) — wire it into both generator families.
3. **STOP and VALIDATE**: run quickstart.md §2–§3; confirm the Dashboard build no longer OOMs. This alone resolves the actively-broken state.

### Incremental Delivery

1. Setup + Foundational → shared utility ready and unit-tested.
2. User Story 1 → Dashboard build unblocked (MVP — the original motivating bug is fixed here).
3. User Story 2 → durability under growth confirmed via synthetic large-group/initiative tests.
4. User Story 3 → stats correctness and audit-log visibility added.
5. Polish → `make ci-check` clean, final end-to-end validation recorded.

---

## Notes

- [P] tasks touch different files and have no unmet dependencies.
- Every implementation task names its exact target file.
- FR-004 (frozen export file shape) is a constraint every task must respect, not a task of its own — code review / T019's lint-type-test gate is what enforces it, since no schema/shape change is possible without breaking existing tests that assert the shape.
