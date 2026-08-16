import json

import pytest

from src.core.logic.research_group_membership_graphs_manifest_generator import (
    ResearchGroupMembershipGraphsManifestGenerator,
)


class TestResearchGroupMembershipGraphsManifestGenerator:
    def test_generate_writes_empty_manifest_when_graphs_dir_missing(self, tmp_path):
        output_dir = tmp_path / "exports"
        output_dir.mkdir()

        generator = ResearchGroupMembershipGraphsManifestGenerator()
        output_path = output_dir / "research_group_membership_graphs_manifest.json"

        result = generator.generate(
            output_dir=str(output_dir), output_path=str(output_path)
        )

        assert (
            output_path.exists()
        ), "Manifest file must be written even when dir is missing"
        assert result["metadata"]["total_groups"] == 0
        assert result["groups"] == []

        with open(output_path, encoding="utf-8") as f:
            written = json.load(f)
        assert written["metadata"]["total_groups"] == 0
        assert written["groups"] == []

    def test_generate_writes_manifest_with_entries(self, tmp_path):
        output_dir = tmp_path / "exports"
        graphs_dir = output_dir / "research_group_membership_graphs"
        graphs_dir.mkdir(parents=True)

        graph_file = graphs_dir / "group_1.json"
        graph_file.write_text(
            json.dumps(
                {
                    "metadata": {
                        "scope": {
                            "research_group": {
                                "id": 1,
                                "name": "Grupo A",
                                "member_count": 3,
                            }
                        }
                    },
                    "graph_stats": {"nodes": 4, "edges": 3},
                }
            ),
            encoding="utf-8",
        )

        generator = ResearchGroupMembershipGraphsManifestGenerator()
        output_path = output_dir / "research_group_membership_graphs_manifest.json"

        result = generator.generate(
            output_dir=str(output_dir), output_path=str(output_path)
        )

        assert result["metadata"]["total_groups"] == 1
        assert output_path.exists()

        with open(output_path, encoding="utf-8") as f:
            written = json.load(f)
        assert len(written["groups"]) == 1
        assert written["groups"][0]["id"] == 1
        assert written["groups"][0]["name"] == "Grupo A"

    def test_generate_skips_invalid_graph_files(self, tmp_path):
        output_dir = tmp_path / "exports"
        graphs_dir = output_dir / "research_group_membership_graphs"
        graphs_dir.mkdir(parents=True)

        (graphs_dir / "bad.json").write_text("{invalid json", encoding="utf-8")
        (graphs_dir / "not_graph.txt").write_text("not json", encoding="utf-8")

        generator = ResearchGroupMembershipGraphsManifestGenerator()
        output_path = output_dir / "research_group_membership_graphs_manifest.json"

        result = generator.generate(
            output_dir=str(output_dir), output_path=str(output_path)
        )

        assert result["metadata"]["total_groups"] == 0
        assert result["groups"] == []
        assert output_path.exists()


@pytest.mark.parametrize("missing", [False, True])
def test_generate_always_writes_file(tmp_path, missing):
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    if not missing:
        (output_dir / "research_group_membership_graphs").mkdir()

    generator = ResearchGroupMembershipGraphsManifestGenerator()
    output_path = output_dir / "research_group_membership_graphs_manifest.json"

    generator.generate(output_dir=str(output_dir), output_path=str(output_path))

    assert output_path.exists()
