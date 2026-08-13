import argparse
import json
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXPECTED_TOP_LEVEL = {
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
    "researchers_tracking.json",
    "initiatives_tracking.json",
    "advisorships_tracking.json",
    "researchers_only_canonical.json",
    "students_canonical.json",
    "outside_ifes_canonical.json",
    "null_researchers_canonical.json",
    "advisorship_analytics.json",
    "knowledge_areas_mart.json",
    "initiatives_analytics_mart.json",
    "people_relationship_graph.json",
    "students_relationship_graph.json",
    "researchers_only_relationship_graph.json",
    "outside_ifes_relationship_graph.json",
    "null_researchers_relationship_graph.json",
    "research_group_relationship_graphs_manifest.json",
    "research_group_membership_graphs_manifest.json",
    "people_collaboration_graph.json",
    "researchers_only_collaboration_graph.json",
    "students_collaboration_graph.json",
    "outside_ifes_collaboration_graph.json",
    "null_researchers_collaboration_graph.json",
    "awards_canonical.json",
    "languages_canonical.json",
    "proficiencies_canonical.json",
    "professional_activities_canonical.json",
    "production_authors_canonical.json",
    "production_types_canonical.json",
    "research_productions_canonical.json",
}

SUBGRAPH_DIR = "research_group_relationship_graphs"


def _validate_zip(archive_path: str) -> list[str]:
    errors = []
    with ZipFile(archive_path) as zf:
        names = zf.namelist()
        top_level = {n.rstrip("/") for n in names if "/" not in n and n}

        missing = EXPECTED_TOP_LEVEL - top_level
        if missing:
            errors.append(f"Missing expected files: {sorted(missing)}")

        extra = top_level - EXPECTED_TOP_LEVEL
        if extra:
            errors.append(f"Unexpected top-level files: {sorted(extra)}")

        sub_files = [
            n for n in names if n.startswith(f"{SUBGRAPH_DIR}/") and n.endswith(".json")
        ]
        if not sub_files:
            errors.append(f"No JSON files found in {SUBGRAPH_DIR}/")

        if "research_group_relationship_graphs_manifest.json" in names:
            manifest = json.loads(
                zf.read("research_group_relationship_graphs_manifest.json")
            )
            manifest_count = len(manifest["graphs"])
            if manifest_count != len(sub_files):
                errors.append(
                    f"Relationship manifest lists {manifest_count} graphs, "
                    f"but {SUBGRAPH_DIR}/ has {len(sub_files)} files"
                )

    return errors


def _clean_symlinks(output_path: Path) -> None:
    for child in output_path.iterdir():
        if child.is_symlink():
            try:
                target = child.readlink()
                print(f"Removing symlink: {child.name} -> {target}")
                child.unlink()
            except OSError:
                pass


def create_export_zip(output_dir: str, dry_run: bool = False) -> str:
    output_path = Path(output_dir).resolve()

    _clean_symlinks(output_path)

    json_files = sorted(output_path.rglob("*.json"))

    if not json_files:
        print(f"No JSON files found in {output_path}; nothing to zip.")
        return ""

    archive_name = "export.zip"
    archive_path = output_path / archive_name

    if dry_run:
        print(f"[DRY RUN] Would create {archive_path} with {len(json_files)} files:")
        for f in json_files:
            print(f"  {f.relative_to(output_path)}")
        print(f"[DRY RUN] Would then delete these {len(json_files)} loose files")
        return str(archive_path)

    print(f"Creating {archive_path} with {len(json_files)} files...")

    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zf:
        for f in json_files:
            arcname = str(f.relative_to(output_path))
            zf.write(f, arcname)

    print(f"Archive created: {archive_path}")

    errors = _validate_zip(str(archive_path))
    if errors:
        print("ZIP validation errors:")
        for e in errors:
            print(f"  - {e}")
        archive_path.unlink()
        print(f"Archive deleted due to validation failures.")
        return ""

    for f in json_files:
        f.unlink()

    for dirpath, dirnames, filenames in os.walk(output_path, topdown=False):
        if dirpath == str(output_path):
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass

    _clean_symlinks(output_path)

    print(f"Loose JSON files removed. Only {archive_name} remains.")

    return str(archive_path)


def main():
    parser = argparse.ArgumentParser(
        description="Zip canonical JSON exports and clean up loose files."
    )
    parser.add_argument("output_dir", help="Directory containing the JSON files to zip")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.output_dir):
        print(f"Error: {args.output_dir} is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    result = create_export_zip(args.output_dir, dry_run=args.dry_run)
    if not result:
        sys.exit(0)


if __name__ == "__main__":
    main()
