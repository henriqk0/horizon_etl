# Research & Architectural Decisions: Automated Export ZIP Extraction & Cache Bootstrapping

## Technical Decisions

### 1. Archive Discovery & Resolution Logic

- **Decision**: Scan `data/exports/` for files matching `canonical_export_*.zip` or `exports_canonical.zip`, sorting matching files by modification time (`mtime`) descending to select the newest archive. If no matching archive is found in `data/exports/`, repeat the search in the project root directory (`./`).
- **Rationale**: Completely dependency-free and automated. Supports both automated pipeline-generated archives in `data/exports/` and user-placed root archives. Sorting by `mtime` guarantees the system always bootstraps from the latest available execution state.
- **Alternatives Considered**:
  - *Hardcoded filename*: Rejected because export archives use dynamic timestamps (`canonical_export_YYYYMMDD_HHMMSS.zip`).
  - *Environment variable explicit path*: Rejected because it requires manual operator configuration, violating automated execution requirements.

### 2. Decompression Engine & File Overwrite Policy

- **Decision**: Decompress using Python's standard `zipfile.ZipFile` module. Extract files into `data/exports/`. For files that already exist locally (such as `data/exports/project_sigpesq_files_json/PJ_*.json`), overwrite only if the archived file is valid and non-empty, preserving existing disk state.
- **Rationale**: Python `zipfile` is built-in, cross-platform (Linux/macOS/Docker), fast (< 1s for 15MB archives), and requires no external binaries (`unzip` executable).
- **Alternatives Considered**:
  - *Shell command `unzip`*: Rejected to avoid OS binary dependency differences between Linux environments and Docker containers.

### 3. Pipeline Integration Architecture

- **Decision**: Implement a reusable logic class `ExportCacheBootstrapper` in `src/core/logic/export_cache_bootstrapper.py` and expose it as a Prefect task `bootstrap_export_cache_task` in `src/flows/exports/canonical_data.py`. Invoke this task at the beginning of `run_weekly()` in `weekly_orchestrator.py` and `app.py` before source ingestion flows run.
- **Rationale**: Adheres strictly to Constitution Principle I (Ports & Adapters) and Principle III (Prefect Flow Orchestration). Placing core logic in `src/core/logic/` allows lightweight unit testing without external services.

### 4. Archive Retention Policy

- **Decision**: Retain the source ZIP archive intact in place after successful extraction.
- **Rationale**: Preserves the original backup archive on disk as requested in clarification Q2.
