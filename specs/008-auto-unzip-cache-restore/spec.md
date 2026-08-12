# Feature Specification: Automated Export ZIP Extraction & Cache Bootstrapping

**Feature Branch**: `008-auto-unzip-cache-restore`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "/speckit-specify Implementar descompactação automática do último ZIP de exportação no início do pipeline para restauração de cache da Mistral AI e dados canônicos"

## Clarifications

### Session 2026-08-12

- Q: Onde o sistema deve procurar pelo arquivo ZIP de exportação anterior para descompactar? → A: Procurar primeiro em `data/exports/` e fazer fallback para a raiz do projeto (`./`) caso `data/exports/` não contenha ZIP.
- Q: O arquivo ZIP de origem deve ser mantido ou removido após a descompactação bem-sucedida? → A: Manter o arquivo ZIP de origem intacto no local após a extração.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Cache Bootstrapping on Pipeline Start (Priority: P1) 🎯 MVP

As a pipeline operator or automated CI/CD schedule, when I trigger `make weekly-flows` or the weekly orchestrator, the system automatically checks for the latest pre-existing export ZIP in `data/exports/` (falling back to project root `./`) and unpacks it before any extraction or API calls run, restoring extracted Mistral AI JSON reports and canonical manifests into local disk cache.

**Why this priority**: Solves manual intervention requirements and prevents redundant, expensive Mistral AI API calls across isolated weekly pipeline runs.

**Independent Test**: Place `canonical_export_20260811_150631.zip` in `data/exports/` (or project root), run orchestrator bootstrap task, and verify `data/exports/project_sigpesq_files_json/` and canonical files are automatically restored without manual user commands.

**Acceptance Scenarios**:

1. **Given** a pre-existing export archive (`canonical_export_*.zip` or `exports_canonical.zip`) in `data/exports/` or project root, **When** the weekly pipeline begins initialization, **Then** the system automatically extracts the archive into `data/exports/` before source ingestion flows start.
2. **Given** the restored `data/exports/project_sigpesq_files_json/` directory with prior extractions, **When** `SigPesqAdapter` or `SigPesqProjectExtractor` runs with `skip_existing=True`, **Then** it skips AI processing for all previously extracted project PDFs.

---

### User Story 2 - Safe Graceful Fallback when No ZIP Exists (Priority: P2)

As a pipeline operator running the system in a clean environment for the first time without prior export ZIP archives, the system logs an informational warning and proceeds cleanly with full ingestion without raising unhandled exceptions or halting execution.

**Why this priority**: Guarantees that new environments or clean initial runs remain 100% operational.

**Independent Test**: Run pipeline initialization in an empty `data/exports/` directory with no ZIP files, verifying that an info log is emitted and execution continues from scratch.

**Acceptance Scenarios**:

1. **Given** an empty `data/exports/` directory with zero `.zip` files, **When** the pipeline bootstrap task executes, **Then** it logs an info message ("No prior export ZIP found; starting with empty export cache.") and proceeds without error.

---

### Edge Cases

- What happens when multiple timestamped `canonical_export_YYYYMMDD_HHMMSS.zip` files exist? The system MUST sort by filename/modification time and pick the most recent archive.
- How does the system handle corrupted or partially downloaded ZIP files? The system MUST catch ZipFile decompression errors, log a warning, and proceed cleanly without crashing the pipeline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST check for pre-existing export archives matching `canonical_export_*.zip` or `exports_canonical.zip` first in `data/exports/`, falling back to searching the project root directory (`./`) if `data/exports/` contains no ZIP archives.
- **FR-002**: System MUST select the most recent ZIP archive if multiple matching archives are present.
- **FR-003**: System MUST automatically extract the selected ZIP archive into `data/exports/` in background prior to running source extraction tasks.
- **FR-004**: System MUST log clear informational messages when an archive is successfully restored or when no archive is available.
- **FR-005**: System MUST NOT overwrite newer extracted local files if a local file with a newer modification timestamp already exists in `data/exports/project_sigpesq_files_json/`.
- **FR-006**: System MUST gracefully handle decompression errors (e.g. truncated ZIP) by logging a warning and proceeding with available local files.
- **FR-007**: System MUST retain the source ZIP archive file intact in place after successful extraction without deleting or moving it.

### Key Entities *(include if feature involves data)*

- **Export Archive**: Timestamped `.zip` file containing canonical JSON files, relationship graphs, manifests, and `project_sigpesq_files_json/*.json` reports.
- **Bootstrap Cache Task**: Prefect task / orchestrator pre-step responsible for archive selection and automatic decompression.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of previously extracted Mistral AI JSON project reports in the latest ZIP are restored into `data/exports/project_sigpesq_files_json/` before SigPesq extraction starts.
- **SC-002**: Redundant Mistral AI API calls for previously processed project PDFs are reduced to 0 during pipeline execution when a prior ZIP is present.
- **SC-003**: Pipeline initialization adds less than 3 seconds of overhead to the total weekly run time.

## Assumptions

- Target environment has read/write permissions in `data/exports/`.
- `zipfile` standard Python library is used for extraction.
- Standard naming convention `canonical_export_YYYYMMDD_HHMMSS.zip` or `exports_canonical.zip` is maintained across all export tasks.
