# Contract: ZIP Fallback & Resilient Export

## CLI & Task Contracts

### 1. `scripts/export_zip.py`
- **Invocation**: `python scripts/export_zip.py <output_dir> [--dry-run]`
- **Input**: Directory path containing canonical JSON exports (e.g. `data/exports`).
- **Behavior**:
  1. Scans `output_dir` for all `.json` files (including subdirectories like `project_sigpesq_files_json/`).
  2. Ignores all `.zip` files in `output_dir`.
  3. Creates `canonical_export_<timestamp>.zip`.
  4. Validates top-level canonical files.
  5. If optional subgraphs are missing, logs warning to stdout without deleting the ZIP.
  6. Returns exit code 0 on success.

### 2. `zip_exports_task` (Prefect Task in `src/flows/exports/canonical_data.py`)
- **Invocation**: `zip_exports_task(output_dir="data/exports")`
- **Output**: `data/exports/exports_canonical.zip`
- **Behavior**:
  - Traverses `output_dir` recursively.
  - Excludes any existing `.zip` files (`fname.endswith(".zip")`).
  - Writes all `.json` files and subdirectories to `exports_canonical.zip`.
  - Atomically replaces `exports_canonical.zip`.
