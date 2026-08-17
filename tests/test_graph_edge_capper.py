import networkx as nx

from src.core.logic.graph_edge_capper import cap_node_degree


def _star_graph(center_weight_pairs):
    """Builds a graph with one center node connected to several neighbors,
    each edge carrying the given weight."""
    graph = nx.Graph()
    graph.add_node("center")
    for neighbor, weight in center_weight_pairs:
        graph.add_node(neighbor)
        graph.add_edge("center", neighbor, weight=weight)
    return graph


def _suppress_reciprocation(graph, node, distractor_prefix):
    """Gives `node` 3 other edges heavier than anything it already has, so
    its own top-3 ranking excludes its existing (weaker) edges — used to
    isolate the union rule's behavior to the *other* endpoint's choice."""
    for i in range(3):
        distractor = f"{distractor_prefix}_{i}"
        graph.add_node(distractor)
        graph.add_edge(node, distractor, weight=10_000 + i)


def test_node_with_fewer_than_cap_relationships_keeps_all_of_them():
    graph = _star_graph([("a", 5), ("b", 3)])

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert result.graph.number_of_nodes() == 3
    assert set(result.graph.neighbors("center")) == {"a", "b"}
    assert result.removed_edge_count == 0


def test_keeps_only_top_n_highest_weight_edges_per_node():
    graph = _star_graph([("a", 10), ("b", 9), ("c", 8), ("d", 7), ("e", 1)])
    # d and e must not be able to independently keep their edge to "center"
    # via their own top-3 — give them stronger connections elsewhere so the
    # outcome depends purely on "center"'s own top-3 choice.
    _suppress_reciprocation(graph, "d", "d_distractor")
    _suppress_reciprocation(graph, "e", "e_distractor")

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert set(result.graph.neighbors("center")) == {"a", "b", "c"}
    assert "d" not in result.graph.neighbors("center")
    assert "e" not in result.graph.neighbors("center")


def test_tie_break_is_deterministic_by_ascending_neighbor_id():
    graph = nx.Graph()
    for neighbor in (10, 20, 30, 40):
        graph.add_edge(1, neighbor, weight=5)
        _suppress_reciprocation(graph, neighbor, f"distractor_{neighbor}")

    result_a = cap_node_degree(graph, max_edges_per_node=3)
    result_b = cap_node_degree(graph, max_edges_per_node=3)

    assert set(result_a.graph.neighbors(1)) == {10, 20, 30}
    assert set(result_a.graph.neighbors(1)) == set(result_b.graph.neighbors(1))


def test_union_rule_keeps_edge_chosen_by_only_one_endpoint():
    graph = nx.Graph()
    # A's strongest connection is B, but B has three stronger connections
    # than A (C, D, E), so B's own top-3 doesn't include A.
    graph.add_edge("A", "B", weight=10)
    graph.add_edge("B", "C", weight=100)
    graph.add_edge("B", "D", weight=90)
    graph.add_edge("B", "E", weight=80)

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert "B" in result.graph.neighbors("A")
    assert "A" in result.graph.neighbors("B")
    # B ends up with 4 retained edges (more than the cap) because A's
    # top-3 choice is honored even though B didn't reciprocate.
    assert set(result.graph.neighbors("B")) == {"A", "C", "D", "E"}


def test_isolated_node_with_no_relationships_is_preserved():
    graph = nx.Graph()
    graph.add_node("lonely")
    graph.add_edge("a", "b", weight=1)

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert "lonely" in result.graph.nodes()
    assert result.graph.degree("lonely") == 0


def test_node_left_isolated_by_trimming_is_still_present():
    graph = _star_graph([("a", 10), ("b", 9), ("c", 8), ("d", 7)])
    # d loses its only edge to "center" (and gains none of its own, since
    # its distractors aren't part of the graph we're measuring degree on),
    # but must still appear in the trimmed graph.
    _suppress_reciprocation(graph, "d", "d_distractor")

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert "d" in result.graph.nodes()
    assert "center" not in result.graph.neighbors("d")


def test_edge_cap_result_stats_are_correct():
    graph = _star_graph([("a", 10), ("b", 9), ("c", 8), ("d", 7), ("e", 1)])
    _suppress_reciprocation(graph, "d", "d_distractor")
    _suppress_reciprocation(graph, "e", "e_distractor")

    result = cap_node_degree(graph, max_edges_per_node=3)

    # 5 center-* edges + 3 distractor edges each for d and e = 11 originally.
    assert result.original_edge_count == 11
    # center keeps 3 (a,b,c); d and e each keep their 3 distractor edges;
    # center-d and center-e are dropped = 2 removed.
    assert result.trimmed_edge_count == 9
    assert result.removed_edge_count == 2
    assert round(result.reduction_pct, 2) == round(2 / 11 * 100, 2)


def test_empty_graph_reduction_pct_avoids_division_by_zero():
    graph = nx.Graph()
    graph.add_node("solo")

    result = cap_node_degree(graph, max_edges_per_node=3)

    assert result.original_edge_count == 0
    assert result.reduction_pct == 0.0
