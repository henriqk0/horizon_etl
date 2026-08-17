import json

from src.core.logic.people_collaboration_graph_generator import (
    PeopleCollaborationGraphGenerator,
)


def _write_researchers(tmp_path, people):
    path = tmp_path / "researchers.json"
    path.write_text(json.dumps(people, ensure_ascii=False), encoding="utf-8")
    return path


def _basic_people():
    # Carla (id=3) is listed before Ana (id=1) so that, by the time Ana's
    # advisorship entry references her, her node already exists in the
    # graph — the generator only adds an edge if both endpoints' nodes
    # were already created (a pre-existing, order-dependent behavior of
    # PeopleCollaborationGraphGenerator.generate, unrelated to this
    # feature's edge-capping change).
    return [
        {
            "id": 3,
            "name": "Carla",
            "classification": "student",
            "initiatives": [{"id": 100}],
            "articles": [{"id": 500}],
            "advisorships": [],
        },
        {
            "id": 1,
            "name": "Ana",
            "classification": "researcher",
            "initiatives": [{"id": 100}],
            "articles": [],
            "advisorships": [{"person_id": 3}],
        },
        {
            "id": 2,
            "name": "Bruno",
            "classification": "student",
            "initiatives": [{"id": 100}],
            "articles": [{"id": 500}],
            "advisorships": [],
        },
    ]


def test_people_collaboration_graph_generator_aggregates_evidence(tmp_path):
    researchers_path = _write_researchers(tmp_path, _basic_people())
    output_path = tmp_path / "people_collaboration_graph.json"

    generator = PeopleCollaborationGraphGenerator()
    result = generator.generate(
        researchers_path=str(researchers_path), output_path=str(output_path)
    )

    assert output_path.exists()
    assert result["graph_stats"]["nodes"] == 3
    edges_by_pair = {
        tuple(sorted((edge["source"], edge["target"]))): edge
        for edge in result["graph"]["edges"]
    }
    assert edges_by_pair[(1, 2)]["initiative_count"] == 1
    assert edges_by_pair[(2, 3)]["article_count"] == 1
    assert edges_by_pair[(1, 3)]["advisorship_count"] == 1


def test_people_collaboration_graph_caps_edges_per_node(tmp_path):
    # A "hub" person collaborating with far more than 3 others via the same
    # initiative — without the cap this would be a 21-edge clique.
    people = [
        {
            "id": 0,
            "name": "Hub",
            "classification": "researcher",
            "initiatives": [{"id": 900}],
            "articles": [],
            "advisorships": [],
        }
    ]
    for i in range(1, 8):
        people.append(
            {
                "id": i,
                "name": f"Person {i}",
                "classification": "researcher",
                "initiatives": [{"id": 900}],
                "articles": [],
                "advisorships": [],
            }
        )
    researchers_path = _write_researchers(tmp_path, people)
    output_path = tmp_path / "capped.json"

    generator = PeopleCollaborationGraphGenerator()
    result = generator.generate(
        researchers_path=str(researchers_path), output_path=str(output_path)
    )

    assert result["graph_stats"]["nodes"] == 8
    # Without capping this is a full 8-node clique: 8*7/2 = 28 edges. All
    # edges here share the same weight, so the union rule (an edge survives
    # if EITHER endpoint's own top-3 keeps it) lets the lowest-id nodes
    # accumulate extra reciprocated edges — that's expected (see
    # test_graph_edge_capper.py's dedicated union-rule tests) — but the
    # result must still be far short of the original 28-edge clique.
    assert result["graph_stats"]["edges"] < 28


def test_people_collaboration_graph_stats_match_trimmed_graph(tmp_path):
    people = _basic_people()
    for i in range(4, 12):
        people.append(
            {
                "id": i,
                "name": f"Extra {i}",
                "classification": "researcher",
                "initiatives": [{"id": 100}],
                "articles": [],
                "advisorships": [],
            }
        )
    researchers_path = _write_researchers(tmp_path, people)
    output_path = tmp_path / "stats_check.json"

    generator = PeopleCollaborationGraphGenerator()
    result = generator.generate(
        researchers_path=str(researchers_path), output_path=str(output_path)
    )

    edges = result["graph"]["edges"]
    nodes = result["graph"]["nodes"]

    assert result["graph_stats"]["nodes"] == len(nodes)
    assert result["graph_stats"]["edges"] == len(edges)

    recounted_initiative_total = sum(e.get("initiative_count", 0) for e in edges)
    recounted_article_total = sum(e.get("article_count", 0) for e in edges)
    recounted_advisorship_total = sum(e.get("advisorship_count", 0) for e in edges)
    assert (
        result["graph_stats"]["relation_event_totals"]["initiative"]
        == recounted_initiative_total
    )
    assert (
        result["graph_stats"]["relation_event_totals"]["article"]
        == recounted_article_total
    )
    assert (
        result["graph_stats"]["relation_event_totals"]["advisorship"]
        == recounted_advisorship_total
    )

    recounted_degree = {}
    for edge in edges:
        recounted_degree[edge["source"]] = recounted_degree.get(edge["source"], 0) + 1
        recounted_degree[edge["target"]] = recounted_degree.get(edge["target"], 0) + 1
    for node in nodes:
        assert node["degree"] == recounted_degree.get(node["id"], 0)


def test_large_initiative_edge_count_stays_bounded_not_quadratic(tmp_path):
    member_count = 500
    people = [
        {
            "id": i,
            "name": f"Member {i}",
            "classification": "researcher",
            "initiatives": [{"id": 1}],
            "articles": [],
            "advisorships": [],
        }
        for i in range(member_count)
    ]
    researchers_path = _write_researchers(tmp_path, people)
    output_path = tmp_path / "large.json"

    generator = PeopleCollaborationGraphGenerator()
    result = generator.generate(
        researchers_path=str(researchers_path), output_path=str(output_path)
    )

    # Without capping, a 500-member clique would have ~124,750 edges
    # (500 * 499 / 2). Capped, it must stay in the same order of magnitude
    # as the node count, not anywhere near the uncapped clique size.
    assert result["graph_stats"]["nodes"] == member_count
    assert result["graph_stats"]["edges"] < member_count * 4
