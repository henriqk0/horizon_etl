# Feature Specification: ZIP Fallback and Multi-Attempt Data Resilience

## Executive Summary
This feature ensures that when any individual pipeline step fails (such as an external source like SigPesq being offline), the pipeline gracefully reuses cached data from previous runs and guarantees that the final export ZIP archive (`exports_canonical.zip` and timestamped canonical exports) is always created and made available in `data/exports/`.

---

## Clarifications

### Session 2026-08-11
- Q: Como o módulo de empacotamento deve se comportar quando o diretório opcional de grafos de relacionamento estiver vazio? → A: Option A - Converter erros de validação de diretórios de grafos opcionais em warnings no log e manter o arquivo ZIP gerado.
- Q: Como os arquivos .json soltos na pasta data/exports/ devem ser tratados após a criação do arquivo ZIP? → A: Option B - Remover os arquivos .json soltos após criar o .zip apenas em execuções de produção/CLI (scripts/export_zip.py), mantendo os arquivos soltos em ambiente de desenvolvimento.

---

## User Scenarios & Testing

### User Story 1 - Graceful Fallback on External Portal Failures (Priority: High)
As a data engineer or ETL operator,
I want the pipeline to automatically fall back to cached raw and export files from previous runs when an external portal (like SigPesq) is unreachable,
So that the overall ETL pipeline completes without abandoning the entire execution.

#### Acceptance Criteria
- **Scenario 1.1**: When SigPesq or another external portal returns connection errors, the pipeline logs a warning and proceeds using available local files in `data/raw/` and `data/exports/project_sigpesq_files_json/`.
- **Scenario 1.2**: Data from previous successful extractions is preserved and reused to populate database entities and canonical export files.

---

### User Story 2 - Guaranteed ZIP Archive Creation (Priority: High)
As an ETL consumer or downstream consumer of exported data,
I want the export ZIP archive (`exports_canonical.zip` / `canonical_export_*.zip`) to be generated reliably even when optional subgraphs or partial step outputs are missing,
So that I always receive a usable ZIP bundle containing all available canonical JSON files.

#### Acceptance Criteria
- **Scenario 2.1**: The ZIP creation task (`export_zip` / `zip_exports_task`) converts missing optional graph folder errors into non-blocking log warnings and preserves the generated `.zip` archive without deletion.
- **Scenario 2.2**: All available canonical files (`initiatives_canonical.json`, `researchers_canonical.json`, `project_sigpesq_files_json/*.json`, etc.) are packaged into the ZIP archive.
- **Scenario 2.3**: If non-critical graph manifest files or subfolders are empty, warnings are logged while keeping the ZIP archive intact.
- **Scenario 2.4**: Loose JSON files in `data/exports/` are preserved during development pipeline runs and optionally cleaned up during production/CLI archive generation tasks.

---

## Functional Requirements

- **FR-001**: The pipeline MUST reuse cached raw data (`data/raw/`) and extracted JSON files (`data/exports/project_sigpesq_files_json/`) whenever an external portal connection fails.
- **FR-002**: The ZIP export module (`scripts/export_zip.py` and `zip_exports_task`) MUST NOT delete generated `.zip` files when optional directories (such as empty relationship graph folders) produce validation warnings, treating them as non-blocking log warnings instead.
- **FR-003**: The pipeline MUST ensure `exports_canonical.zip` contains all top-level canonical JSON files and subfolder JSONs present in `data/exports/`.
- **FR-004**: The weekly orchestrator MUST report step execution warnings while continuing to generate downstream artifacts (marts and ZIPs) from available data.
- **FR-005**: Loose JSON files in `data/exports/` MUST be retained during dev runs and cleaned up only when production CLI zipping (`scripts/export_zip.py --clean-loose`) is explicitly triggered.

---

## Success Criteria

- **SC-001**: 100% of pipeline executions produce a valid ZIP export file in `data/exports/` regardless of individual external portal connectivity failures.
- **SC-002**: 100% of previously extracted project JSONs and cached raw files are preserved and packaged into the final ZIP archive when an external source step fails.
- **SC-003**: Downstream consumers can extract `exports_canonical.zip` and access all available canonical dataset files without manual intervention.

---

## Assumptions & Boundaries

- **Assumptions**:
  - `data/raw/` and `data/exports/project_sigpesq_files_json/` contain persistent data from previous successful extractions.
  - Optional graph subdirectories (e.g. `research_group_relationship_graphs/`) are not strictly required for top-level canonical data consumers.
- **Out of Scope**:
  - Inventing fake/synthetic data when neither live portal access nor local cached files exist.
