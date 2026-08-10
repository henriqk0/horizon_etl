# Research & Decision Log: SigPesq PDF Download & Mistral Report Extraction

**Feature Branch**: `006-sigpesq-pdf-mistral-extraction`  
**Date**: 2026-08-10  

## Technical Decisions

### 1. Browser Download Strategy for Project PDFs

- **Decision**: Use `ProjectFilesDownloadStrategy` from `agent_sigpesq.strategies` combined with `SigpesqReportService`.
- **Rationale**: The `sigpesq_agent` library already implements the Playwright-based navigation to search project grids, open the Resumo modal, click download links, and store raw PDFs on disk (`data/raw/sigpesq/projects/`).
- **Alternatives Considered**:
  - *Custom Playwright script*: Rejected as redundant since `sigpesq_agent` provides a tested strategy.

### 2. Extraction Component & Execution Modes (Mistral AI)

- **Decision**: Create an adapter component in `src/adapters/sources/sigpesq/` wrapping `ProjectExtractor` and `BatchProjectExtractor` from `agent_sigpesq.extraction`.
- **Rationale**: Keeps external SDK/API interactions encapsulated within `src/adapters/` (enforcing Ports & Adapters architecture per Constitution Principle I). Allows seamless switching between synchronous mode (`ProjectExtractor`) for smaller/dev runs and Batch API mode (`BatchProjectExtractor`) when `use_batch=True`.
- **Alternatives Considered**:
  - *Calling `sigpesq_agent` directly inside logic or flow*: Rejected to avoid violating Constitution Principle I.

### 3. Prefect Flow & Integration with Existing Enrichment

- **Decision**: Implement a Prefect flow `extract_projects_flow` in `src/flows/sigpesq/extract_projects.py` registered with `telegram_flow_state_handlers()`. The flow orchestrates:
  1. Validation of environment variables (`SIGPESQ_USERNAME`, `SIGPESQ_PASSWORD`, `MISTRAL_KEY`).
  2. Downloading PDFs into `data/raw/sigpesq/projects/` via `ProjectFilesDownloadStrategy`.
  3. Extracting structured JSON via Mistral AI into `data/exports/project_sigpesq_files_json/`.
  4. Triggering `enrich_projects_flow` to update database initiatives.
- **Rationale**: Complies with Constitution Principle III (Prefect Flow Orchestration) and completes the end-to-end pipeline.

### 4. Data Quality & Fault Tolerance

- **Decision**:
  - Individual PDF download errors log warnings and skip to the next project without crashing the batch.
  - OCR fallback (`mistral-ocr-latest`) is automatically triggered for scanned PDFs.
  - JSON payloads are validated via Pydantic (`Projeto` model) prior to writing output files.
- **Rationale**: Guarantees high pipeline reliability and data validity per Constitution Principle IV (Audit-Driven Data Quality).
