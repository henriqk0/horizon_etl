# Phase 1 Data Model: Cap Relationship Graph Edges

This feature does not introduce new persisted domain entities (per Constitution Principle II, no new canonical entity is defined — graphs are a derived analytics artifact). It introduces one new in-memory/return-value structure and leaves the existing exported JSON shape untouched.

## Existing Entities (unchanged shape, referenced for context)

### Graph Export File (`{metadata, graph_stats, graph}`)

Already produced by both generator families via `networkx.readwrite.json_graph.node_link_data`. Untouched by this feature — FR-004 requires byte-for-byte-compatible shape, only the *contents* of `graph.edges` (and the counts inside `graph_stats`) change.

| Field | Type | Notes |
|---|---|---|
| `metadata.generated_at` | string (ISO 8601) | unchanged |
| `metadata.weight_definition` | string | unchanged — describes the existing weight formula, not modified by this feature |
| `graph_stats.nodes` | int | now counts nodes in the **trimmed** graph (identical to before trimming, since FR-006 keeps all nodes) |
| `graph_stats.edges` | int | now counts edges in the **trimmed** graph — this is the number that shrinks |
| `graph_stats.top_people_by_weighted_degree` | array | now computed from trimmed weighted degree |
| `graph.nodes` | array | unchanged — same node set, same attributes |
| `graph.edges` | array | now the trimmed edge set (≤3 per node, plus any union-rule additions per FR-007) |

### Person (node)

Unchanged. `id`, `name`, `classification`, `classification_confidence`, `was_student`, `was_staff`, `campus_name`, `degree`, `weighted_degree` — all recomputed against the trimmed graph where applicable (`degree`/`weighted_degree`), everything else passthrough.

### Connection (edge)

Unchanged fields (`weight`, `initiative_count`/`research_group_count`/`advisorship_count` or `initiative_count`/`article_count`/`advisorship_count`, `relation_types`). Only the *set* of which edges exist changes — no edge's own fields are modified by trimming.

## New Structure: `EdgeCapResult`

Returned by the new shared trimming function (`src/core/logic/graph_edge_capper.py`). Purely an internal return value — never serialized directly into an export file; its fields feed the log line described in research.md's Decision 5 (FR-008/SC-006).

| Field | Type | Description |
|---|---|---|
| `graph` | `networkx.Graph` | The trimmed graph — same nodes as input, edge set reduced per the capping rule. |
| `original_edge_count` | int | Edge count of the graph *before* trimming. |
| `trimmed_edge_count` | int | Edge count *after* trimming (`len(graph.edges)`). |
| `removed_edge_count` | int | `original_edge_count - trimmed_edge_count`. |
| `reduction_pct` | float | `removed_edge_count / original_edge_count * 100` (0.0 if `original_edge_count` is 0 — avoids division by zero for empty/tiny graphs). |

## Validation Rules (from Functional Requirements)

- Every node present in the input graph MUST be present in the output graph (FR-006) — trimming never removes a node, even one left with zero edges.
- No node's retained edge count is *reduced* below what its own top-3 selection produced (FR-007's union rule: a node's own top-3 always survives regardless of what neighbors decided).
- Given the same input graph, the function MUST produce an identical output graph on every call (FR-003/SC-005) — no randomness, no dependency on dict/set iteration order for the ranking decision itself (Python 3.7+ dict ordering is insertion-order-stable, but the *sort* — not iteration order — is what determines the result here, per Decision 2's explicit `(weight, neighbor_id)` sort key).
