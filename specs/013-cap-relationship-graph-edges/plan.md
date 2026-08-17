# Implementation Plan: Cap Relationship Graph Edges

**Branch**: `013-cap-relationship-graph-edges` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-cap-relationship-graph-edges/spec.md`

## Summary

Every relationship/collaboration graph exporter builds a full clique of edges for every group of co-occurring people (same initiative, same research group, same advisorship), causing O(n²) edge growth per group/initiative. Confirmed on real data: the global relationship graph is 455MB, the researchers-only variant is 215MB, and the 344 per-research-group graphs total 627MB (up to 31MB for a single group) — large enough to make the downstream Dashboard's production build fail with an out-of-memory error even at 16GB of heap. The fix adds a shared, reusable post-processing step — applied uniformly to every graph export just before it's serialized to JSON — that keeps, for each person, only their 3 highest-weight connections, unioned with any connection where the *other* endpoint chose them back (per the union rule in FR-007). Graph statistics are recomputed from the trimmed graph, and each export logs how many edges were removed and the resulting size reduction. The JSON shape consumed by the Dashboard does not change — only the number of edges inside `graph.edges` shrinks.

## Technical Context

**Language/Version**: Python ≥3.10 (project-wide `pyproject.toml` constraint; this repo's active venv runs 3.14)

**Primary Dependencies**: networkx ≥3.4.0 (graph construction/serialization already in use by both generator families), loguru (existing logging convention), Prefect (existing flow/task orchestration — no new flows needed, only task-level changes)

**Storage**: N/A — this feature only transforms in-memory graph objects before they're written to the existing JSON export files under `data/exports/`; no database changes.

**Testing**: pytest (project standard); new unit tests live in `tests/` alongside existing generator tests

**Target Platform**: Linux server (same weekly-pipeline execution environment as the rest of the ETL)

**Project Type**: Single project — internal ETL library/CLI (no frontend/backend split; this feature is entirely inside `src/core/logic/`)

**Performance Goals**: The trimming step must not meaningfully change the `people_relationship_graph` phase's existing runtime budget (1800s timeout in `weekly_orchestrator.py`, currently completing in ~154s per a real production run) — trimming a graph with ~10k nodes and its existing edge count is a single linear pass per node, not expected to be the bottleneck.

**Constraints**: Exported JSON shape (`{metadata, graph_stats, graph: {nodes, edges}}`, i.e. `networkx.readwrite.json_graph.node_link_data` output) MUST NOT change — the Dashboard (a separate repository) statically imports and parses these files today and must keep working unmodified.

**Scale/Scope**: ~10,089 researchers, ~4,692 initiatives, 344 research groups in the current real dataset (basis for the 455MB/215MB/627MB measurements this feature must bring down).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Ports & Adapters Architecture**: PASS. This feature is entirely internal business logic in `src/core/logic/` (graph generators). No adapter or port changes.
- **II. Domain-First Data Modeling**: PASS. No new domain entities are introduced; graph nodes/edges are a derived analytics artifact, not a canonical domain entity, and the exported shape is unchanged.
- **III. Prefect Flow Orchestration**: PASS. No new flows. The trimming step is added inside existing tasks (`generate_people_relationship_graph_task` and the four collaboration-graph tasks), which already run inside Prefect flows with Telegram state hooks.
- **IV. Audit-Driven Data Quality**: PASS — this feature directly serves this principle. FR-008/SC-006 add a verifiable audit signal (edges removed, reduction %) for every export, following the same pattern as the `unresolved_count` reporting added for research group institutional filtering (spec 011).
- **V. LGPD Compliance by Default**: PASS. No new personal-data fields are introduced or exposed; trimming only removes edges, and the existing anonymization behavior for node attributes (names, etc.) is untouched.
- **Development Workflow & Quality Gates**: New/modified code MUST pass `make ci-check` (flake8, black, isort, mypy, pytest) and MUST include new tests per the "new flows MUST have a corresponding test" principle, extended here to "modified generators MUST have a corresponding test."

No violations requiring justification — Complexity Tracking section is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/013-cap-relationship-graph-edges/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/             # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/core/logic/
├── graph_edge_capper.py                       # NEW — shared trimming utility used by every graph generator
├── people_relationship_graph_generator.py      # MODIFIED — applies the cap before serializing full/classification/per-group graphs
├── people_collaboration_graph_generator.py     # MODIFIED — applies the cap before serializing the global graph
├── researchers_collaboration_graph_generator.py   # unchanged (subclasses the base — inherits the fix)
├── students_collaboration_graph_generator.py      # unchanged (subclasses the base — inherits the fix)
├── outside_ifes_collaboration_graph_generator.py  # unchanged (subclasses the base — inherits the fix)
└── null_researchers_collaboration_graph_generator.py  # unchanged (subclasses the base — inherits the fix)

src/flows/exports/
└── (unchanged — trim-stats logging lives in the two generator classes below, not in the flow task wrappers; all four collaboration flows inherit it for free via the shared base class)

tests/
├── test_graph_edge_capper.py                     # NEW — unit tests for the shared trimming utility
├── test_people_relationship_graph_generator.py    # MODIFIED — assert trimming + stats consistency (create if it doesn't exist yet)
└── test_people_collaboration_graph_generator.py   # MODIFIED — same, for the collaboration family
```

**Structure Decision**: Single project (existing `src/core/logic/` + `src/flows/exports/` layout). The fix is a new, small, dependency-free utility module consumed by both existing generator families, keeping the change surgical and avoiding any restructuring of the two generator class hierarchies.

## Complexity Tracking

*No constitution violations — table not needed.*
