import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def create_export_zip(output_dir: str, dry_run: bool = False) -> str:
    output_path = Path(output_dir).resolve()

    json_files = sorted(output_path.rglob("*.json"))

    if not json_files:
        print(f"No JSON files found in {output_path}; nothing to zip.")
        return ""

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"canonical_export_{ts}.zip"
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

    for f in json_files:
        f.unlink()

    for dirpath, dirnames, filenames in os.walk(output_path, topdown=False):
        if dirpath == str(output_path):
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass

    print(f"Loose JSON files removed. Only {archive_name} remains.")

    return str(archive_path)


def main():
    parser = argparse.ArgumentParser(description="Zip canonical JSON exports and clean up loose files.")
    parser.add_argument("output_dir", help="Directory containing the JSON files to zip")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    if not os.path.isdir(args.output_dir):
        print(f"Error: {args.output_dir} is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    result = create_export_zip(args.output_dir, dry_run=args.dry_run)
    if not result:
        sys.exit(0)


if __name__ == "__main__":
    main()
