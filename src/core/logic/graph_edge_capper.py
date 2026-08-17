"""Per-node degree capping for relationship/collaboration graph exports.

Both graph generator families (people_relationship_graph_generator.py and
people_collaboration_graph_generator.py) build a full clique of edges for
every group of co-occurring people (shared initiative, shared research
group, advisorship), which grows O(n^2) with group size. This module trims
each node down to its strongest few connections before the graph is
serialized, without changing the exported file's shape.
"""

from dataclasses import dataclass
from typing import Any

import networkx as nx


@dataclass
class EdgeCapResult:
    graph: nx.Graph
    original_edge_count: int
    trimmed_edge_count: int
    removed_edge_count: int
    reduction_pct: float


def cap_node_degree(graph: nx.Graph, max_edges_per_node: int = 3) -> EdgeCapResult:
    """Return a trimmed copy of `graph` keeping only each node's strongest
    `max_edges_per_node` connections (by edge weight), unioned with any edge
    where the other endpoint kept it in their own top-N (so a connection
    survives if at least one of its two endpoints chose it).

    Every original node is preserved, even ones left with zero edges after
    trimming. Ties on weight are broken by ascending neighbor node id, so
    the result is deterministic across repeated runs on unchanged data.
    """
    original_edge_count = graph.number_of_edges()

    kept_edges: set[tuple[Any, Any]] = set()
    for node in graph.nodes():
        neighbors = [
            (graph[node][neighbor].get("weight", 0), neighbor)
            for neighbor in graph.neighbors(node)
        ]
        neighbors.sort(key=lambda item: (-item[0], item[1]))
        for _weight, neighbor in neighbors[:max_edges_per_node]:
            kept_edges.add(tuple(sorted((node, neighbor), key=str)))

    trimmed = nx.Graph()
    trimmed.add_nodes_from(graph.nodes(data=True))
    for source, target in kept_edges:
        trimmed.add_edge(source, target, **graph[source][target])

    trimmed_edge_count = trimmed.number_of_edges()
    removed_edge_count = original_edge_count - trimmed_edge_count
    reduction_pct = (
        (removed_edge_count / original_edge_count * 100.0)
        if original_edge_count
        else 0.0
    )

    return EdgeCapResult(
        graph=trimmed,
        original_edge_count=original_edge_count,
        trimmed_edge_count=trimmed_edge_count,
        removed_edge_count=removed_edge_count,
        reduction_pct=reduction_pct,
    )
