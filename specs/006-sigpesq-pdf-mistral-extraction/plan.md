# Implementation Plan: SigPesq PDF Download & Mistral Report Extraction

**Branch**: `006-sigpesq-pdf-mistral-extraction` | **Date**: 2026-08-10 | **Spec**: [specs/006-sigpesq-pdf-mistral-extraction/spec.md](specs/006-sigpesq-pdf-mistral-extraction/spec.md)

**Input**: Feature specification from `/specs/006-sigpesq-pdf-mistral-extraction/spec.md`

## Summary

Implement automated download of research project PDF documents from the SigPesq portal using Playwright (`ProjectFilesDownloadStrategy`), followed by structured data extraction via Mistral AI (`ProjectExtractor` and `BatchProjectExtractor` with OCR fallback for scanned PDFs). Output JSON reports in `data/exports/project_sigpesq_files_json/` and integrate execution with the Prefect enrichment flow (`enrich_projects_flow`).

## Technical Context

**Language/Version**: Python 3.14  

**Primary Dependencies**: `sigpesq-agent` (branch `feat/project-pdf-download-and-mistral-extraction`), `playwright`, `mistralai`, `pypdf`, `pydantic`, `prefect`, `loguru`  

**Storage**: Local raw storage (`data/raw/sigpesq/projects/`), export JSON files (`data/exports/project_sigpesq_files_json/`), SQLite DB (`db/horizon.db`)  

**Testing**: `pytest` (`tests/test_sigpesq_project_extraction.py`, `tests/test_project_enrichment.py`)  

**Target Platform**: Linux / macOS / Docker  

**Project Type**: ETL Pipeline / CLI / Prefect Flow  

**Performance Goals**: Process ~100 project PDFs per batch; support Batch API for multi-hundred project runs.  

**Constraints**: Respect SigPesq rate limiting (exponential backoff on HTTP 429); fail fast if credentials/API keys missing; anonymize PII (CPF) per LGPD.  

**Scale/Scope**: ~500 research projects; JSON artifacts ~20KB each.  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Ports & Adapters Architecture (NON-NEGOTIABLE)**: **PASS**  
  External library interactions (`sigpesq_agent`, Playwright, Mistral API) are encapsulated inside `src/adapters/sources/sigpesq/`. Logic in `src/core/logic/` does not import from adapters. Flows in `src/flows/` orchestrate adapters and logic.
- **Principle II: Domain-First Data Modeling**: **PASS**  
  JSON outputs adhere to canonical schemas and map cleanly to initiative enrichment payloads.
- **Principle III: Prefect Flow Orchestration (NON-NEGOTIABLE)**: **PASS**  
  Flow implemented in `src/flows/sigpesq/extract_projects.py` as a Prefect flow registered with `telegram_flow_state_handlers()`.
- **Principle IV: Audit-Driven Data Quality**: **PASS**  
  Extraction metadata (`_meta`) records text source (native vs OCR), pages, timestamp, model, and missing fields for full auditability.
- **Principle V: LGPD Compliance by Default**: **PASS**  
  PII fields (CPF) in extracted team members are masked/anonymized before JSON artifacts are saved to `data/exports/`.

## Project Structure

### Documentation (this feature)

```text
specs/006-sigpesq-pdf-mistral-extraction/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── flow_contract.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/
├── adapters/
│   └── sources/
│       └── sigpesq/
│           ├── adapter.py              # Download & extraction triggering adapter
│           └── mistral_extractor.py    # Wrapper for ProjectExtractor & BatchProjectExtractor
├── core/
│   ├── logic/
│   │   ├── loaders.py                  # File loader for SigPesq JSONs
│   │   └── project_enrichment.py       # Initiative matching & enrichment logic
│   └── ports/
│       └── source.py                   # ISource interface
└── flows/
    └── sigpesq/
        ├── extract_projects.py         # New Prefect flow (Download + Mistral + Enrich)
        └── enrich_projects.py          # Existing enrichment flow

tests/
├── unit/
│   └── test_sigpesq_project_extraction.py
└── test_project_enrichment.py
```

**Structure Decision**: Single ETL pipeline project following the existing `src/adapters/`, `src/core/`, `src/flows/` layout.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | Fully compliant with Horizon ETL Constitution |
