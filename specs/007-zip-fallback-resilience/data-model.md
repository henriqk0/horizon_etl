# Data Model & Artifact Schema: ZIP Fallback and Multi-Attempt Data Resilience

## Transient Entities & Artifact Schemas

### 1. Export Archive Artifact (`exports_canonical.zip` / `canonical_export_*.zip`)
- **Type**: ZIP Archive File
- **Location**: `data/exports/`
- **Contents**:
  - `initiatives_canonical.json` (Required)
  - `researchers_canonical.json` (Required)
  - `advisorships_canonical.json` (Required)
  - `articles_canonical.json` (Required)
  - `organizations_canonical.json` (Required)
  - `project_sigpesq_files_json/*.json` (Required when project extractions exist)
  - `research_group_relationship_graphs/*.json` (Optional; empty/missing logs warning)
- **Validation Rules**:
  - All core canonical JSON files present at top-level -> Valid.
  - Subgraph JSON files present or missing -> Valid (logs warning if missing).
  - No nested `.zip` files included inside the archive.

### 2. Pipeline Step Outcome
- **State**: `SUCCESS` | `WARNING` | `FAILED`
- **Fallback Behavior**:
  - If `SigPesq` live download fails AND cached raw/JSON files exist -> State becomes `WARNING`, execution continues to `extract_projects_flow` and `export_canonical_data_flow`.
  - If `SigPesq` live download fails AND NO cached files exist -> State becomes `FAILED`.
