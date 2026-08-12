# Implementation Plan: ZIP Fallback and Multi-Attempt Data Resilience

**Branch**: `007-zip-fallback-resilience` | **Date**: 2026-08-11 | **Spec**: [specs/007-zip-fallback-resilience/spec.md](spec.md)

**Input**: Feature specification from `/specs/007-zip-fallback-resilience/spec.md`

## Summary

This feature enhances the Horizon ETL export and fallback architecture to guarantee that:
1. `scripts/export_zip.py` and Prefect `zip_exports_task` create and preserve the export ZIP archive (`exports_canonical.zip` / `canonical_export_*.zip`) without unlinking it when optional subgraphs (like empty relationship graph folders) produce non-fatal validation warnings.
2. In-memory and disk-cached extractions (such as `data/exports/project_sigpesq_files_json/*.json` and raw files) are preserved and reused when an external source (like SigPesq portal) is unreachable, allowing downstream canonical exports and ZIP generation to complete cleanly.

## Technical Context

**Language/Version**: Python 3.14  
**Primary Dependencies**: Prefect, PyPDF / Mistral API, SQLite, Standard Library `zipfile`  
**Storage**: SQLite (`db/horizon.db`), File System (`data/exports/`, `data/raw/`)  
**Testing**: pytest  
**Target Platform**: Linux Server  
**Project Type**: ETL Data Pipeline CLI / Prefect Flows  
**Performance Goals**: Export zipping < 5 seconds for ~400 JSON files  
**Constraints**: Zero data loss for previously extracted JSONs; non-destructive validation for optional subgraphs  
**Scale/Scope**: ~350+ project JSONs, 4200+ canonical initiative records  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Ports & Adapters Architecture**: PASS (Logic mediated through port contracts; adapters handle storage and file system zipping).
- **Principle II: Domain-First Data Modeling**: PASS (Canonical JSON exports serialize domain-aligned entities).
- **Principle III: Prefect Flow Orchestration**: PASS (Export zipping and fallback logic runs within Prefect flows under `src/flows/`).
- **Principle IV: Audit-Driven Data Quality**: PASS (ZIP validation logs non-fatal warnings for audit trail without unlinking valid output).
- **Principle V: LGPD Compliance by Default**: PASS (All canonical exports and project JSONs pass through CPF anonymization).
- **Data Integrity & Clean-State Ingestion**: PASS (Reuses valid local state when live portal fails).
- **Development Workflow & Quality Gates**: PASS (`make ci-check` passes).

## Project Structure

### Documentation (this feature)

```text
specs/007-zip-fallback-resilience/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── flow_contract.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
scripts/
└── export_zip.py                             # Modifies _validate_zip to treat missing subgraphs as warnings

src/
├── adapters/
│   └── sources/
│       └── sigpesq/
│           └── adapter.py                    # Ensures fallback to cached JSON extractions on network failure
└── flows/
    └── exports/
        └── canonical_data.py                 # Modifies zip_exports_task to ignore .zip files during traversal

tests/
└── test_zip_fallback.py                      # Test suite for ZIP validation warnings & fallback behavior
```

**Structure Decision**: Standard single project structure using `scripts/`, `src/adapters/`, `src/flows/`, and `tests/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | Fully compliant with architecture |
