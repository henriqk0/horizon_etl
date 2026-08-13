# Implementation Plan: Per-Phase ZIP Fallback Seeding & Data Provenance Reporting

**Branch**: `009-per-phase-fallback-provenance` | **Date**: 2026-08-13 | **Spec**: [specs/009-per-phase-fallback-provenance/spec.md](spec.md)

**Input**: Feature specification from `/specs/009-per-phase-fallback-provenance/spec.md`

## Summary

Implement per-phase data fallback seeding and data provenance tracking across all weekly ETL pipeline phases. When a source ingestion phase (SigPesq, CNPq, Lattes) encounters live portal downtime or zero items, `CanonicalDatabaseSeeder` automatically populates the SQLite database (`horizon.db`) with entities from prior canonical export JSONs (`research_groups_canonical.json`). Each phase records its data origin (`LIVE`, `ZIP ANTERIOR`, `PARCIAL`, or `VAZIO`) in a provenance marker, and `weekly_orchestrator` renders the origin tags in the final CLI summary table and Telegram completion notifications.

## Technical Context

**Language/Version**: Python 3.14+ / 3.11+

**Primary Dependencies**: Prefect 3.x, `research-domain`, `loguru`, standard library `pathlib` / `json`

**Storage**: SQLite database (`horizon.db`), local JSON export artifacts (`data/exports/`)

**Testing**: Pytest (`tests/test_provenance_and_seeder.py`)

**Target Platform**: Linux server / Docker container / local dev

**Project Type**: ETL pipeline / Prefect orchestration flow

**Performance Goals**: Provenance recording and database seeding adds less than 1 second of total overhead

**Constraints**: Zero data loss, preserves live-updated records without overwriting newer data, zero breaking changes to existing Prefect task definitions

**Scale/Scope**: 12 weekly pipeline phases, 350+ project JSON reports, ~50 research groups

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Ports & Adapters)**: PASS — Core seeding logic in `src/core/logic/canonical_database_seeder.py` uses domain controllers without direct adapter imports.
- **Principle II (Domain-First)**: PASS — Maps canonical export JSON entities into `research-domain` entities.
- **Principle III (Prefect Orchestration)**: PASS — Preserves Prefect flow wrappers and state change notification hooks.
- **Principle IV (Audit-Driven Quality)**: PASS — Records data provenance per phase and reports origin in CLI summary and Telegram messages.
- **Principle V (LGPD Compliance)**: PASS — Operates on domain entities and anonymized export artifacts.

## Project Structure

### Documentation (this feature)

```text
specs/009-per-phase-fallback-provenance/
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
│       ├── canonical_database_seeder.py   # Database seeder from export JSONs
│       └── provenance_tracker.py          # Provenance marker reader/writer
└── flows/
    ├── cnpq/
    │   └── groups.py                     # Triggers database seeder before group sync
    ├── sources/
    │   └── sigpesq/
    │       └── adapter.py                # Sets ZIP ANTERIOR provenance on fallback
    └── pipelines/
        └── weekly_orchestrator.py        # Reads provenance markers and prints tags

tests/
└── test_provenance_and_seeder.py         # Unit tests for seeder and provenance
```

**Structure Decision**: Single project layout matching existing ports & adapters architecture.

## Complexity Tracking

> No constitution violations.
