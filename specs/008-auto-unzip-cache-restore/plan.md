# Implementation Plan: Automated Export ZIP Extraction & Cache Bootstrapping

**Branch**: `008-auto-unzip-cache-restore` | **Date**: 2026-08-12 | **Spec**: [specs/008-auto-unzip-cache-restore/spec.md](spec.md)

**Input**: Feature specification from `/specs/008-auto-unzip-cache-restore/spec.md`

## Summary

Implement an automated pre-ingestion cache bootstrapper (`ExportCacheBootstrapper`) that scans `data/exports/` (falling back to project root `./`) for pre-existing export archives (`canonical_export_*.zip` or `exports_canonical.zip`). When found, the bootstrapper automatically extracts its contents into `data/exports/` in background before any source ingestion flows or AI extractions run. This restores `data/exports/project_sigpesq_files_json/` and canonical manifests, allowing the Mistral AI extractor to skip redundant processing of previously extracted project PDFs without manual user intervention.

## Technical Context

**Language/Version**: Python 3.14+ / 3.11+

**Primary Dependencies**: Prefect 3.x, standard library `zipfile`, `loguru`

**Storage**: Local disk filesystem (`data/exports/`, `data/exports/project_sigpesq_files_json/`)

**Testing**: Pytest (`tests/test_auto_unzip_bootstrap.py`)

**Target Platform**: Linux server / Docker container / local dev

**Project Type**: ETL pipeline / Prefect orchestration flow

**Performance Goals**: Decompression and cache bootstrapping overhead under 3 seconds

**Constraints**: Zero mandatory OS external binary dependencies (pure Python `zipfile`), zero data loss, retains source ZIP archive file intact after extraction

**Scale/Scope**: 350+ JSON project files (~15MB ZIP archive size)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Ports & Adapters)**: PASS — Core bootstrap logic implemented in `src/core/logic/export_cache_bootstrapper.py` without external adapter imports.
- **Principle II (Domain-First)**: PASS — Restores domain-aligned canonical JSON exports and project extractions.
- **Principle III (Prefect Orchestration)**: PASS — Exposed as a Prefect task `bootstrap_export_cache_task` in `src/flows/exports/canonical_data.py`.
- **Principle IV (Audit-Driven Quality)**: PASS — Logs detailed audit metrics (archive selected, file count extracted, warnings).
- **Principle V (LGPD Compliance)**: PASS — Restores anonymized canonical exports and masked JSON reports.

## Project Structure

### Documentation (this feature)

```text
specs/008-auto-unzip-cache-restore/
├── plan.md              # This file
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
├── core/
│   └── logic/
│       └── export_cache_bootstrapper.py   # Core ZIP discovery & extraction logic
└── flows/
    ├── exports/
    │   └── canonical_data.py             # Contains bootstrap_export_cache_task
    └── pipelines/
        └── weekly_orchestrator.py        # Invokes bootstrap before phase runs

tests/
└── test_auto_unzip_bootstrap.py         # Unit tests for bootstrap logic
```

**Structure Decision**: Single project layout matching existing ports & adapters architecture.

## Complexity Tracking

> No constitution violations.
