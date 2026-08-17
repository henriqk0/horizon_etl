# Contract: `graph_edge_capper` module

This feature has no external HTTP/CLI surface. Its two relevant contracts are (1) the new internal function signature both generator families call, and (2) the frozen external file-format contract with the Dashboard consumer.

## 1. Internal function contract

**Module**: `src/core/logic/graph_edge_capper.py`

```python
def cap_node_degree(
    graph: networkx.Graph,
    max_edges_per_node: int = 3,
) -> EdgeCapResult:
    """
    Returns a new graph containing every node from `graph`, and an edge set
    limited so that each node retains at most its `max_edges_per_node`
    highest-weight incident edges — unioned with any edge where the other
    endpoint's own top-N selection includes this node (FR-007 union rule).

    Deterministic: given the same input graph, always returns the same
    output graph (ties on weight broken by ascending neighbor node id).

    Never removes a node, even one left with zero retained edges.
    """
```

**Preconditions**:
- `graph` is a `networkx.Graph` (undirected) where every edge has a numeric `weight` attribute (already guaranteed by both existing generator families before this feature).

**Postconditions**:
- `result.graph.number_of_nodes() == graph.number_of_nodes()` (FR-006).
- For every node `n` in `graph` with at least one edge, at least `min(max_edges_per_node, degree(n))` of `n`'s original highest-weight edges are present in `result.graph` (FR-007's per-node guarantee).
- `result.graph` contains no edge absent from the original `graph` (trimming only removes, never adds new relationships).
- `result.original_edge_count == graph.number_of_edges()`.
- `result.trimmed_edge_count == result.graph.number_of_edges()`.
- Calling `cap_node_degree(graph)` twice on the same untouched `graph` object produces two graphs with identical node sets and identical edge sets (SC-005).

**Call sites** (both existing, both call this function immediately before serialization, replacing the graph object passed downstream):
- `PeopleRelationshipGraphGenerator._serialize_graph_result` (covers the full graph, the 4 classification subgraphs, and each of the 344 per-research-group subgraphs — same call site reused per FR-002's uniformity requirement).
- `PeopleCollaborationGraphGenerator.generate` (covers the global graph and, via inheritance, all 4 classification-filtered collaboration exports).

## 2. External file-format contract (frozen — not modified by this feature)

**Consumer**: `horizon_dashboard_h` (separate repository), via static imports (`researchers/[id].astro`, `groups/[id].astro`, `students/[id].astro`) and glob-imports (`../../data/research_group_relationship_graphs/*.json`) of the exact node-link JSON shape below.

```json
{
  "metadata": { "...": "unchanged fields" },
  "graph_stats": { "nodes": 0, "edges": 0, "...": "unchanged fields, values now reflect the trimmed graph" },
  "graph": {
    "directed": false,
    "multigraph": false,
    "graph": {},
    "nodes": [ { "id": 0, "...": "unchanged node attributes" } ],
    "edges": [ { "source": 0, "target": 0, "weight": 0, "...": "unchanged edge attributes" } ]
  }
}
```

**Guarantee**: This feature MUST NOT add, remove, or rename any key in this structure, and MUST NOT change any field's type. Only the *number of entries* in `graph.edges` (and the counts derived from it in `graph_stats`) may change. This is what makes the fix backward-compatible with the Dashboard without requiring any changes there (FR-004).
