# Phase 0 Research: Cap Relationship Graph Edges

No unresolved `NEEDS CLARIFICATION` markers remained in the Technical Context after `/speckit-clarify`. This document records the design decisions made to turn the spec's requirements into a concrete approach.

## Decision 1: Where trimming happens — a shared utility, not per-generator logic

**Decision**: Add one new module, `src/core/logic/graph_edge_capper.py`, exposing a single function that takes a built `networkx.Graph` and returns a trimmed copy plus a stats dict. Both `PeopleRelationshipGraphGenerator` and `PeopleCollaborationGraphGenerator` call it right before serialization.

**Rationale**: The spec requires the cap to apply *uniformly* to every relationship and collaboration graph export (FR-002). The two generator families are structurally independent (different classes, different weight formulas, different serialization helpers), so a shared, generator-agnostic function is the only way to guarantee one trimming rule instead of two subtly different reimplementations drifting apart over time. It also gives the four collaboration-graph subclasses (`Researchers`/`Students`/`OutsideIfes`/`NullResearchers`) the fix for free, since they all funnel through the shared base class's `generate()`.

**Alternatives considered**:
- *Trim inside each generator independently*: rejected — duplicates the ranking/tie-break/union logic in two places, and the four collaboration subclasses would each need their own copy unless they go through the shared base (which they already do, so no extra work there — but relationship vs. collaboration would still diverge).
- *Trim at the graph-construction stage (skip adding low-weight edges as they're discovered)*: rejected — a person's final top-3 can't be known until every initiative/group/advisorship touching them has been processed (weight accumulates incrementally via `_increment_edge`/`_add_evidence`), so ranking must happen after the graph is fully built, not during construction.

## Decision 2: Ranking key and deterministic tie-break

**Decision**: For each node, sort its incident edges by `(weight, neighbor_node_id)` descending on weight and ascending on neighbor id, then take the first 3. Neighbor id (already a stable integer person id) is the tie-break key.

**Rationale**: Weight is the spec's explicit ranking basis (FR-001). FR-003 requires a deterministic tie-break so re-running the export on unchanged data is reproducible (SC-005) — neighbor id is already a stable, always-present integer on every node, so it needs no new data and sorts identically on every run.

**Alternatives considered**:
- *Tie-break by name*: rejected — names aren't guaranteed unique or stable in formatting (accents/casing), unlike the numeric person id.
- *Insertion order*: rejected — depends on the iteration order of source JSON lists, which is not guaranteed stable across regenerations from the same logical data (e.g. if an upstream export re-serializes records in a different order).

## Decision 3: Union rule implementation

**Decision**: Compute each node's top-3 neighbor-id set independently, then the kept edge set for the whole graph is the union of `{(node, neighbor) for neighbor in node.top3}` across all nodes. An edge survives if it appears in at least one node's top-3 (matches the clarified FR-007 union rule). Build the trimmed graph as a subgraph containing only kept edges, but **all** original nodes (so isolated nodes introduced by trimming, or already-isolated nodes, are never dropped — FR-006).

**Rationale**: Directly implements the clarified answer. Computing per-node top-3 sets first (before unioning) is the natural way to guarantee every node retains its own strongest 3 relationships regardless of what the other endpoint decided, which was the explicit reason the union rule was chosen over intersection.

**Alternatives considered**: Intersection rule — explicitly rejected by the user during clarification (§ FR-007) because it could silently drop a well-connected person's strongest relationship if the counterpart didn't reciprocate.

## Decision 4: Recomputing `graph_stats` post-trim

**Decision**: Both generators already build their `graph_stats` dict (node/edge counts, degree distributions, `top_people_by_weighted_degree`, relation-event totals, etc.) via helper methods that operate on whatever `nx.Graph` object they're given. No new stats logic is needed — simply call those existing helpers on the *trimmed* graph object instead of the original, after trimming.

**Rationale**: Satisfies FR-005 with the smallest possible change — the existing stats-computation code is already generator-agnostic with respect to the input graph object.

## Decision 5: Reporting trim impact (FR-008 / SC-006)

**Decision**: The shared trimming function returns a stats dict (`{original_edges, trimmed_edges, removed_edges, reduction_pct}`) alongside the trimmed graph. Each generator logs this via `logger.info(...)` right where it already logs its "N nodes, M edges" summary line — `people_relationship_graph_generator.py`'s `generate`/`generate_all` (once per full/classification/per-group graph) and `people_collaboration_graph_generator.py`'s single `generate()` method. Because all four collaboration-graph subclasses (`Researchers`/`Students`/`OutsideIfes`/`NullResearchers`) call this same inherited `generate()`, one change there covers all four — no per-flow-task changes needed. This follows the exact pattern already established for `research_group_exporter.py`'s `unresolved_count` warning (spec 011) — a structured log line inside the existing Prefect task, which is what already surfaces as visible output in the weekly run's captured logs.

**Rationale**: Matches an existing, already-accepted codebase convention rather than inventing a new reporting channel (e.g. a new manifest file or a new column in the `weekly_orchestrator.py` summary table), keeping the change minimal and consistent.

**Alternatives considered**: Adding a new field to `weekly_orchestrator.py`'s per-phase summary table — rejected as unnecessarily invasive for this feature; that table currently only reports phase name/status/duration, and threading trim stats through it would require plumbing return values across a subprocess boundary (each phase runs in a separate subprocess) for no benefit over a log line that's already captured per-phase.

## Decision 6: Per-research-group graphs use the same function, per group

**Decision**: `_export_research_group_graphs` (in `people_relationship_graph_generator.py`) calls the shared trimming function on each group's induced subgraph individually, right before that group's `_serialize_graph_result` call — the same call site pattern as the full/classification graphs, just once per group in the existing loop.

**Rationale**: Keeps the fix for the largest offender (627MB across 344 files, up to 31MB per group) exactly consistent with every other graph export, per FR-002's uniformity requirement. Trimming the per-group subgraph (rather than trimming the full global graph once and then slicing) is necessary because a person's top-3 *within a specific group's context* can legitimately differ from their top-3 in the full population graph (documented as an accepted assumption in the spec) — group membership already restricts the candidate pool before trimming even applies.
