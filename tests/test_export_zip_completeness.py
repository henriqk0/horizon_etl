import json
import re
import zipfile
from pathlib import Path

EXPORTS_DIR = Path("data/exports")


def _resolve_zip() -> Path:
    ts_zips = sorted(p for p in EXPORTS_DIR.glob("canonical_export_*.zip"))
    if ts_zips:
        return ts_zips[-1]
    fallback = EXPORTS_DIR / "exports_canonical.zip"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        "No canonical_export_*.zip or exports_canonical.zip found " f"in {EXPORTS_DIR}"
    )


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
}

SUBGRAPH_DIR = "research_group_relationship_graphs"


def test_zip_exists():
    path = _resolve_zip()
    assert path.exists(), f"ZIP not found at {path}"


def test_zip_contains_all_expected_top_level():
    with zipfile.ZipFile(_resolve_zip()) as zf:
        names = zf.namelist()

    top_level = {n.rstrip("/") for n in names if "/" not in n and n}

    missing = EXPECTED_TOP_LEVEL - top_level
    extra = top_level - EXPECTED_TOP_LEVEL

    assert not missing, f"Missing expected top-level files: {sorted(missing)}"
    assert not extra, f"Unexpected top-level files: {sorted(extra)}"


def test_zip_subgraph_directory_matches_relationship_manifest():
    with zipfile.ZipFile(_resolve_zip()) as zf:
        names = zf.namelist()
        manifest = json.loads(
            zf.read("research_group_relationship_graphs_manifest.json")
        )
        manifest_paths = {g["path"] for g in manifest["graphs"]}
        actual_files = {
            n for n in names if n.startswith(f"{SUBGRAPH_DIR}/") and n.endswith(".json")
        }

    assert len(manifest["graphs"]) > 0, "Manifest lists no graphs"
    assert manifest_paths == actual_files, (
        f"Manifest lists {len(manifest_paths)} graphs, "
        f"directory contains {len(actual_files)}. "
        f"Missing from dir: {manifest_paths - actual_files}. "
        f"Extra in dir: {actual_files - manifest_paths}."
    )


def test_zip_membership_manifest_count_matches_relationship_dir():
    with zipfile.ZipFile(_resolve_zip()) as zf:
        names = zf.namelist()
        mem_manifest = json.loads(
            zf.read("research_group_membership_graphs_manifest.json")
        )
        rel_manifest = json.loads(
            zf.read("research_group_relationship_graphs_manifest.json")
        )

        mem_count = mem_manifest["metadata"]["total_groups"]
        rel_count = len(rel_manifest["graphs"])
        actual_files = {
            n for n in names if n.startswith(f"{SUBGRAPH_DIR}/") and n.endswith(".json")
        }

    assert mem_count > 0, "Membership manifest lists no graphs"
    assert rel_count == mem_count, (
        f"Relationship manifest has {rel_count} graphs, "
        f"but membership manifest expects {mem_count}"
    )
    assert len(actual_files) == rel_count, (
        f"Relationship manifest ({rel_count}) vs "
        f"actual files in {SUBGRAPH_DIR}/ ({len(actual_files)})"
    )


def test_zip_subgraph_directory_has_files():
    with zipfile.ZipFile(_resolve_zip()) as zf:
        names = sorted(zf.namelist())

    sub_files = [
        n for n in names if n.startswith(f"{SUBGRAPH_DIR}/") and n.endswith(".json")
    ]

    assert len(sub_files) > 0, f"No JSON files found in {SUBGRAPH_DIR}/"
