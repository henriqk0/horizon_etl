# Implementation Plan: Student Campus Allocation Hierarchy

**Branch**: `005-student-campus-allocation` | **Date**: 2026-08-05 | **Spec**: [`specs/005-student-campus-allocation/spec.md`](file:///home/rafael/horizon_etl_h/specs/005-student-campus-allocation/spec.md)

**Input**: Feature specification from `/specs/005-student-campus-allocation/spec.md`

## Summary

Redefine how a student's institutional campus is resolved in `horizon_etl` by replacing the single-source (research group only) logic with a 3-tier cascading priority hierarchy: (1) Project/Edital Campuses $\rightarrow$ (2) Research Group Campuses $\rightarrow$ (3) Main Academic Advisor Campuses. Support multi-campus allocation when ties or multiple campus associations exist at the winning priority level, and expose both `campus` (primary) and `campuses` (list) in `students_canonical.json`.

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: SQLAlchemy, Prefect 3, eo_lib, research_domain, loguru  
**Storage**: PostgreSQL / SQLite (via SQLAlchemy)  
**Testing**: pytest (`tests/test_export_campus_resolver.py`, `tests/test_canonical_exporter.py`)  
**Target Platform**: Linux server  
**Project Type**: Data ETL pipeline & JSON Canonical Exporter  
**Performance Goals**: Processing time increase $\le 10\%$ for student campus resolution (SC-004)  
**Constraints**: LGPD anonymization maintained, Ports & Adapters architecture preserved  
**Scale/Scope**: ~6,000 students, 350+ research groups, 3,500+ initiatives  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Ports & Adapters Architecture**: PASS. Resolution logic is encapsulated in `src/core/logic/export_campus_resolver.py` and `canonical_exporter.py`. No direct imports of `src/adapters/`.
- **II. Domain-First Data Modeling**: PASS. Canonical JSON payloads conform to `research-domain` entity definitions.
- **III. Prefect Flow Orchestration**: PASS. Export execution remains integrated within Prefect export flows.
- **IV. Audit-Driven Data Quality**: PASS. Audit provenance metadata (`campus_resolution`) added to every student record.
- **V. LGPD Compliance by Default**: PASS. PII scrubbing (`scrub_pii_deep`) applies to student exports.

## Project Structure

### Documentation (this feature)

```text
specs/005-student-campus-allocation/
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 output (research decisions & rationale)
├── data-model.md        # Phase 1 output (canonical JSON schema & resolver data map)
├── quickstart.md        # Phase 1 output (runnable validation guide)
├── contracts/           # Phase 1 output (JSON schema contract)
│   └── students-canonical-export.json
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code (repository root)

```text
src/
└── core/
    └── logic/
        ├── export_campus_resolver.py  # 3-tier cascade & multi-campus map logic
        └── canonical_exporter.py      # Enriches student JSON export with campus & resolution audit

tests/
├── test_export_campus_resolver.py     # Unit tests for 3-tier cascade and tie-breaker
└── test_canonical_exporter.py          # Integration tests for student canonical export
```

**Structure Decision**: Single project architecture. All updates target `src/core/logic/` and `tests/`.

## Complexity Tracking

> *No constitution violations. All checks passed cleanly.*
