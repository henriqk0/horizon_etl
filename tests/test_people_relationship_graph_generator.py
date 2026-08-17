import json

from src.core.logic.people_relationship_graph_generator import (
    PeopleRelationshipGraphGenerator,
)


def _write_sample_inputs(tmp_path, include_null_person: bool = False):
    researchers = [
        {
            "id": 1,
            "name": "Ana",
            "classification": "researcher",
            "classification_confidence": "high",
            "was_student": False,
            "was_staff": True,
            "campus": {"id": 10, "name": "Serra"},
        },
        {
            "id": 2,
            "name": "Bruno",
            "classification": "student",
            "classification_confidence": "high",
            "was_student": True,
            "was_staff": False,
            "campus": {"id": 10, "name": "Serra"},
        },
        {
            "id": 3,
            "name": "Carla",
            "classification": "student",
            "classification_confidence": "medium",
            "was_student": True,
            "was_staff": False,
            "campus": None,
        },
    ]

    if include_null_person:
        researchers.append(
            {
                "id": 4,
                "name": "Dora",
                "classification": None,
                "classification_confidence": "low",
                "was_student": False,
                "was_staff": False,
                "campus": None,
            }
        )

    fixtures = {
        "researchers.json": researchers,
        "initiatives.json": [
            {
                "id": 100,
                "name": "Projeto 1",
                "team": [
                    {"person_id": 1, "person_name": "Ana"},
                    {"person_id": 2, "person_name": "Bruno"},
                    {"person_id": 3, "person_name": "Carla"},
                ],
            }
        ],
        "research_groups.json": [
            {
                "id": 200,
                "name": "Grupo 1",
                "short_name": "G1",
                "members": [
                    {"id": 1, "name": "Ana"},
                    {"id": 2, "name": "Bruno"},
                ],
            }
        ],
        "advisorships.json": [
            {
                "id": 300,
                "name": "Projeto com bolsa",
                "advisorships": [
                    {
                        "id": 400,
                        "person_id": 3,
                        "person_name": "Carla",
                        "supervisor_id": 1,
                        "supervisor_name": "Ana",
                    }
                ],
            }
        ],
    }

    paths = {}
    for filename, payload in fixtures.items():
        path = tmp_path / filename
        path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        paths[filename] = path

    return paths


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_people_relationship_graph_generator_aggregates_relationships(tmp_path):
    paths = _write_sample_inputs(tmp_path)
    output_path = tmp_path / "people_relationship_graph.json"

    generator = PeopleRelationshipGraphGenerator()
    result = generator.generate(
        researchers_path=str(paths["researchers.json"]),
        initiatives_path=str(paths["initiatives.json"]),
        research_groups_path=str(paths["research_groups.json"]),
        advisorships_path=str(paths["advisorships.json"]),
        output_path=str(output_path),
    )

    assert output_path.exists()
    assert result["graph_stats"]["nodes"] == 3
    assert result["graph_stats"]["edges"] == 3
    assert result["graph_stats"]["relation_event_totals"] == {
        "initiative": 3,
        "research_group": 1,
        "advisorship": 1,
    }

    nodes_by_id = {node["id"]: node for node in result["graph"]["nodes"]}
    assert nodes_by_id[1]["weighted_degree"] == 4
    assert nodes_by_id[2]["classification"] == "student"
    assert nodes_by_id[3]["campus_name"] is None

    edges_by_pair = {
        tuple(sorted((edge["source"], edge["target"]))): edge
        for edge in result["graph"]["edges"]
    }

    assert edges_by_pair[(1, 2)]["weight"] == 2
    assert edges_by_pair[(1, 2)]["initiative_count"] == 1
    assert edges_by_pair[(1, 2)]["research_group_count"] == 1
    assert edges_by_pair[(1, 2)]["advisorship_count"] == 0
    assert edges_by_pair[(1, 2)]["relation_types"] == [
        "initiative",
        "research_group",
    ]

    assert edges_by_pair[(1, 3)]["weight"] == 2
    assert edges_by_pair[(1, 3)]["initiative_count"] == 1
    assert edges_by_pair[(1, 3)]["research_group_count"] == 0
    assert edges_by_pair[(1, 3)]["advisorship_count"] == 1
    assert edges_by_pair[(1, 3)]["relation_types"] == [
        "initiative",
        "advisorship",
    ]

    assert edges_by_pair[(2, 3)]["weight"] == 1
    assert edges_by_pair[(2, 3)]["relation_types"] == ["initiative"]


def test_people_relationship_graph_generator_exports_filtered_graph_files(tmp_path):
    paths = _write_sample_inputs(tmp_path, include_null_person=True)
    output_dir = tmp_path / "exports"

    generator = PeopleRelationshipGraphGenerator()
    result = generator.generate_all(
        researchers_path=str(paths["researchers.json"]),
        initiatives_path=str(paths["initiatives.json"]),
        research_groups_path=str(paths["research_groups.json"]),
        advisorships_path=str(paths["advisorships.json"]),
        output_dir=str(output_dir),
    )

    full_graph_path = output_dir / "people_relationship_graph.json"
    students_graph_path = output_dir / "students_relationship_graph.json"
    researchers_graph_path = output_dir / "researchers_only_relationship_graph.json"
    outside_graph_path = output_dir / "outside_ifes_relationship_graph.json"
    null_graph_path = output_dir / "null_researchers_relationship_graph.json"
    research_group_manifest_path = (
        output_dir / "research_group_relationship_graphs_manifest.json"
    )
    research_group_graph_path = (
        output_dir
        / "research_group_relationship_graphs"
        / "research_group_200_relationship_graph.json"
    )

    assert full_graph_path.exists()
    assert students_graph_path.exists()
    assert researchers_graph_path.exists()
    assert outside_graph_path.exists()
    assert null_graph_path.exists()
    assert research_group_manifest_path.exists()
    assert research_group_graph_path.exists()

    assert result["full_graph_path"] == str(full_graph_path)
    assert len(result["classification_exports"]) == 4
    assert result["research_group_exports"]["manifest_path"] == str(
        research_group_manifest_path
    )

    full_graph = _load_json(full_graph_path)
    students_graph = _load_json(students_graph_path)
    researchers_graph = _load_json(researchers_graph_path)
    outside_graph = _load_json(outside_graph_path)
    null_graph = _load_json(null_graph_path)
    research_group_manifest = _load_json(research_group_manifest_path)
    research_group_graph = _load_json(research_group_graph_path)

    assert full_graph["metadata"]["scope"] == {"type": "full"}
    assert full_graph["graph_stats"]["nodes"] == 4
    assert full_graph["graph_stats"]["isolated_nodes"] == 1

    assert students_graph["metadata"]["scope"] == {
        "type": "classification",
        "classification": "student",
    }
    assert students_graph["graph_stats"]["nodes"] == 2
    assert students_graph["graph_stats"]["edges"] == 1
    assert students_graph["graph_stats"]["classification_distribution"] == {
        "student": 2
    }

    assert researchers_graph["metadata"]["scope"] == {
        "type": "classification",
        "classification": "researcher",
    }
    assert researchers_graph["graph_stats"]["nodes"] == 1
    assert researchers_graph["graph_stats"]["edges"] == 0

    assert outside_graph["metadata"]["scope"] == {
        "type": "classification",
        "classification": "outside_ifes",
    }
    assert outside_graph["graph_stats"]["nodes"] == 0
    assert outside_graph["graph_stats"]["edges"] == 0

    assert null_graph["metadata"]["scope"] == {
        "type": "classification",
        "classification": "null",
    }
    assert null_graph["graph_stats"]["nodes"] == 1
    assert null_graph["graph_stats"]["edges"] == 0
    assert null_graph["graph_stats"]["classification_distribution"] == {"null": 1}

    assert research_group_manifest["metadata"]["scope"] == {
        "type": "research_group_manifest"
    }
    assert research_group_manifest["graphs"] == [
        {
            "id": 200,
            "name": "Grupo 1",
            "short_name": "G1",
            "member_count": 2,
            "expanded_node_count": 3,
            "advisorship_neighbor_count": 1,
            "nodes": 3,
            "edges": 3,
            "path": (
                "research_group_relationship_graphs/"
                "research_group_200_relationship_graph.json"
            ),
        }
    ]

    assert research_group_graph["metadata"]["scope"] == {
        "type": "research_group",
        "research_group": {
            "id": 200,
            "name": "Grupo 1",
            "short_name": "G1",
            "member_count": 2,
            "expanded_node_count": 3,
            "advisorship_neighbor_count": 1,
        },
    }
    assert research_group_graph["graph_stats"]["nodes"] == 3
    assert research_group_graph["graph_stats"]["edges"] == 3
    assert research_group_graph["graph_stats"]["relation_event_totals"] == {
        "initiative": 3,
        "research_group": 1,
        "advisorship": 1,
    }
    nodes_by_id = {node["id"]: node for node in research_group_graph["graph"]["nodes"]}
    assert nodes_by_id[1]["is_group_member"] is True
    assert nodes_by_id[1]["is_advisorship_neighbor"] is False
    assert nodes_by_id[3]["is_group_member"] is False
    assert nodes_by_id[3]["is_advisorship_neighbor"] is True


def _write_large_group_inputs(tmp_path, member_count=500):
    researchers = [
        {
            "id": i,
            "name": f"Member {i}",
            "classification": "researcher",
            "classification_confidence": "high",
            "was_student": False,
            "was_staff": True,
            "campus": None,
        }
        for i in range(member_count)
    ]
    fixtures = {
        "researchers.json": researchers,
        "initiatives.json": [],
        "research_groups.json": [
            {
                "id": 900,
                "name": "Grupo Gigante",
                "short_name": "GG",
                "members": [
                    {"id": i, "name": f"Member {i}"} for i in range(member_count)
                ],
            }
        ],
        "advisorships.json": [],
    }
    paths = {}
    for filename, payload in fixtures.items():
        path = tmp_path / filename
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        paths[filename] = path
    return paths


def test_large_research_group_edge_count_stays_bounded_not_quadratic(tmp_path):
    member_count = 500
    paths = _write_large_group_inputs(tmp_path, member_count)
    output_dir = tmp_path / "exports"

    generator = PeopleRelationshipGraphGenerator()
    generator.generate_all(
        researchers_path=str(paths["researchers.json"]),
        initiatives_path=str(paths["initiatives.json"]),
        research_groups_path=str(paths["research_groups.json"]),
        advisorships_path=str(paths["advisorships.json"]),
        output_dir=str(output_dir),
    )

    group_graph_path = (
        output_dir
        / "research_group_relationship_graphs"
        / "research_group_900_relationship_graph.json"
    )
    group_graph = _load_json(group_graph_path)

    # Without capping, a 500-member clique would have ~124,750 edges
    # (500 * 499 / 2). Capped, it must stay in the same order of magnitude
    # as the node count.
    assert group_graph["graph_stats"]["nodes"] == member_count
    assert group_graph["graph_stats"]["edges"] < member_count * 4


def test_relationship_graph_stats_match_trimmed_graph_after_cap(tmp_path):
    paths = _write_large_group_inputs(tmp_path, member_count=50)
    output_dir = tmp_path / "exports"

    generator = PeopleRelationshipGraphGenerator()
    generator.generate_all(
        researchers_path=str(paths["researchers.json"]),
        initiatives_path=str(paths["initiatives.json"]),
        research_groups_path=str(paths["research_groups.json"]),
        advisorships_path=str(paths["advisorships.json"]),
        output_dir=str(output_dir),
    )

    group_graph_path = (
        output_dir
        / "research_group_relationship_graphs"
        / "research_group_900_relationship_graph.json"
    )
    group_graph = _load_json(group_graph_path)

    nodes = group_graph["graph"]["nodes"]
    edges = group_graph["graph"]["edges"]

    assert group_graph["graph_stats"]["nodes"] == len(nodes)
    assert group_graph["graph_stats"]["edges"] == len(edges)

    recounted_degree = {}
    for edge in edges:
        recounted_degree[edge["source"]] = recounted_degree.get(edge["source"], 0) + 1
        recounted_degree[edge["target"]] = recounted_degree.get(edge["target"], 0) + 1
    for node in nodes:
        assert node["degree"] == recounted_degree.get(node["id"], 0)

    recounted_initiative_total = sum(e.get("initiative_count", 0) for e in edges)
    recounted_group_total = sum(e.get("research_group_count", 0) for e in edges)
    recounted_advisorship_total = sum(e.get("advisorship_count", 0) for e in edges)
    assert (
        group_graph["graph_stats"]["relation_event_totals"]["initiative"]
        == recounted_initiative_total
    )
    assert (
        group_graph["graph_stats"]["relation_event_totals"]["research_group"]
        == recounted_group_total
    )
    assert (
        group_graph["graph_stats"]["relation_event_totals"]["advisorship"]
        == recounted_advisorship_total
    )
