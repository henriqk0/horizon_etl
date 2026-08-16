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


def test_generate_all_preserves_restored_graphs_for_absent_groups(tmp_path):
    """Restored graph files for research groups no longer in the canonical
    export must survive regeneration AND remain listed in the manifest
    (previously _clean_research_group_graphs deleted ALL graph files and the
    rebuilt manifest dropped preserved entries, leaking fallback data)."""
    paths = _write_sample_inputs(tmp_path, include_null_person=True)
    output_dir = tmp_path / "exports"

    graphs_dir = output_dir / "research_group_relationship_graphs"
    graphs_dir.mkdir(parents=True)

    restored = {
        "id": 999,
        "name": "Grupo Restaurado",
        "short_name": "GR",
        "member_count": 2,
        "expanded_node_count": 2,
        "advisorship_neighbor_count": 0,
    }
    restored_path = graphs_dir / "research_group_999_relationship_graph.json"
    restored_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "sources": {},
                    "scope": {
                        "type": "research_group",
                        "research_group": restored,
                    },
                    "weight_definition": "",
                    "relation_types": {},
                },
                "graph_stats": {"nodes": 2, "edges": 0},
                "graph": {"nodes": [], "edges": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    generator = PeopleRelationshipGraphGenerator()
    generator.generate_all(
        researchers_path=str(paths["researchers.json"]),
        initiatives_path=str(paths["initiatives.json"]),
        research_groups_path=str(paths["research_groups.json"]),
        advisorships_path=str(paths["advisorships.json"]),
        output_dir=str(output_dir),
    )

    assert restored_path.exists(), "restored graph for absent group was deleted"
    assert (graphs_dir / "research_group_200_relationship_graph.json").exists()

    manifest = _load_json(
        output_dir / "research_group_relationship_graphs_manifest.json"
    )
    manifest_ids = {g["id"] for g in manifest["graphs"]}
    assert (
        999 in manifest_ids
    ), "restored graph must be listed in manifest so it matches the directory"
    assert 200 in manifest_ids
    restored_entry = next(g for g in manifest["graphs"] if g["id"] == 999)
    assert restored_entry["name"] == "Grupo Restaurado"
    assert restored_entry["path"] == (
        "research_group_relationship_graphs/"
        "research_group_999_relationship_graph.json"
    )
