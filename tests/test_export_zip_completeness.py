import json
import zipfile
from pathlib import Path

ZIP_PATH = "data/exports/exports_canonical.zip"

EXPECTED_TOP_LEVEL = {
    # Canonical entity exports
    "organizations_canonical.json",
    "campuses_canonical.json",
    "knowledge_areas_canonical.json",
    "researchers_canonical.json",
    "research_groups_canonical.json",
    "initiatives_canonical.json",
    "initiative_types_canonical.json",
    "articles_canonical.json",
    "advisorships_canonical.json",
    "ingestion_runs_canonical.json",
    "source_records_canonical.json",
    "entity_matches_canonical.json",
    "attribute_assertions_canonical.json",
    "entity_change_logs_canonical.json",
    "fellowships_canonical.json",
    # Tracking exports
    "researchers_tracking.json",
    "initiatives_tracking.json",
    "advisorships_tracking.json",
    # Researcher classification views
    "researchers_only_canonical.json",
    "students_canonical.json",
    "outside_ifes_canonical.json",
    "null_researchers_canonical.json",
    # Analytics marts
    "advisorship_analytics.json",
    "initiatives_analytics_mart.json",
    "knowledge_areas_mart.json",
    # Relationship graphs
    "people_relationship_graph.json",
    "students_relationship_graph.json",
    "researchers_only_relationship_graph.json",
    "outside_ifes_relationship_graph.json",
    "null_researchers_relationship_graph.json",
    # Research group graph manifests
    "research_group_relationship_graphs_manifest.json",
    "research_group_membership_graphs_manifest.json",
    # Collaboration graphs
    "people_collaboration_graph.json",
    "researchers_only_collaboration_graph.json",
    "students_collaboration_graph.json",
    "outside_ifes_collaboration_graph.json",
    "null_researchers_collaboration_graph.json",
    # Subdirectory entries
    "research_group_relationship_graphs",
    "research_group_membership_graphs",
}

EXPECTED_SUBDIRECTORIES = {
    "research_group_relationship_graphs",
    "research_group_membership_graphs",
}


def test_zip_exists():
    assert Path(ZIP_PATH).exists(), f"ZIP not found at {ZIP_PATH}"


def test_zip_contains_all_expected_top_level():
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()

    prefix = "data/exports/"
    top_level = set()
    for n in names:
        if n.startswith(prefix):
            rel = n[len(prefix) :].rstrip("/")
        else:
            rel = n.rstrip("/")
        if "/" not in rel and rel:
            top_level.add(rel)

    missing = EXPECTED_TOP_LEVEL - top_level
    extra = top_level - EXPECTED_TOP_LEVEL

    assert not missing, f"Missing expected top-level files: {sorted(missing)}"
    unexpected = [e for e in sorted(extra) if e not in EXPECTED_SUBDIRECTORIES]
    assert not unexpected, f"Unexpected top-level files: {unexpected}"


def test_zip_relationship_graph_subdirectory_matches_manifest():
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        manifest = json.loads(
            zf.read("data/exports/research_group_relationship_graphs_manifest.json")
        )
        manifest_paths = {g["path"] for g in manifest["graphs"]}
        actual_files = {
            n[len("data/exports/") :]
            for n in names
            if "research_group_relationship_graphs/" in n and n.endswith(".json")
        }

    assert len(manifest["graphs"]) > 0, "Manifest lists no graphs"
    assert manifest_paths == actual_files, (
        f"Manifest lists {len(manifest_paths)} graphs "
        f"but directory contains {len(actual_files)}"
    )


def test_zip_membership_subdirectory_matches_manifest():
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        manifest = json.loads(
            zf.read("data/exports/research_group_membership_graphs_manifest.json")
        )
        expected_count = manifest["metadata"]["total_groups"]
        actual_files = {
            n[len("data/exports/") :]
            for n in names
            if "research_group_membership_graphs/" in n and n.endswith(".json")
        }

    assert expected_count > 0, "Manifest lists no graphs"
    assert len(actual_files) == expected_count, (
        f"Manifest expects {expected_count} graphs "
        f"but directory contains {len(actual_files)}"
    )


def test_zip_subdirectory_contents_are_identical():
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = sorted(zf.namelist())

    rel_files = [
        n
        for n in names
        if "research_group_relationship_graphs/" in n and n.endswith(".json")
    ]
    mem_files = [
        n
        for n in names
        if "research_group_membership_graphs/" in n and n.endswith(".json")
    ]

    rel_basenames = {n.split("/")[-1] for n in rel_files}
    mem_basenames = {n.split("/")[-1] for n in mem_files}

    assert rel_basenames == mem_basenames, (
        "research_group_relationship_graphs and "
        "research_group_membership_graphs have different file sets"
    )
    assert len(rel_files) > 0, "No files in research_group_relationship_graphs"
