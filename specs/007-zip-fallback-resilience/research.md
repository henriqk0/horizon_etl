# Research: ZIP Fallback and Multi-Attempt Data Resilience

## Research Topics

### 1. ZIP Archive Validation & Deletion in `scripts/export_zip.py`
- **Context**: `scripts/export_zip.py` validates top-level JSONs and subgraphs in `research_group_relationship_graphs/`. If any expected subgraph is missing or empty, `_validate_zip()` returns validation errors, causing `create_export_zip()` to delete `archive_path`.
- **Decision**: Modify `_validate_zip()` to separate fatal errors (missing core canonical files like `initiatives_canonical.json`) from non-fatal warnings (empty optional graph subdirectories). Non-fatal warnings will be logged as warnings while allowing the ZIP creation to complete successfully.
- **Rationale**: Downstream consumers require the core canonical JSONs. Optional subgraphs should not block the creation of the canonical export archive when external sources are offline.
- **Alternatives Considered**: Creating dummy empty JSON arrays `[]` in graph subdirectories; rejected because non-fatal warnings preserve accurate metadata while producing valid ZIP archives.

### 2. Prefect `zip_exports_task` Traversal (`src/flows/exports/canonical_data.py`)
- **Context**: `zip_exports_task` walks `data/exports/` and writes all files to `exports_canonical.zip`.
- **Decision**: Update `zip_exports_task` to explicitly ignore any existing `.zip` files (`fname.endswith(".zip")`) during traversal.
- **Rationale**: Prevents recursive nesting of older timestamped or canonical zip archives inside `exports_canonical.zip`.
- **Alternatives Considered**: Deleting old `.zip` files before zipping; rejected because users may intentionally keep historical timestamped ZIPs in `data/exports/`.

### 3. External Source Fallback Behavior (`src/adapters/sources/sigpesq/adapter.py`)
- **Context**: When SigPesq portal is unreachable (HTTP 5xx, timeout, or login failure), `_trigger_download` raises `RuntimeError` if raw directories are empty.
- **Decision**: Ensure `SigPesqAdapter` checks for existing extracted JSON files (`data/exports/project_sigpesq_files_json/`) as well as raw files before raising a fatal error. If cached extractions or raw files exist, log a warning and allow downstream ingestion/enrichment to continue with cached state.
- **Rationale**: Align with Constitution Principle I & IV by gracefully handling source offline events using persistent local state.
- **Alternatives Considered**: Mocking live responses; rejected because cached disk files contain real historical data.
