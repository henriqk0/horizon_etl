# Feature Specification: SigPesq PDF Download & Mistral Report Extraction

**Feature Branch**: `006-sigpesq-pdf-mistral-extraction`

**Created**: 2026-08-10

**Status**: Draft

**Input**: User description: "Adicionar fluxo de download de PDFs de projetos do SigPesq e extração detalhada de relatórios usando Mistral AI"

## Clarifications

### Session 2026-08-10

- Q: Modo de execução da extração com Mistral AI (Síncrono vs. Lote/Batch) → A: Opção A - Suportar parâmetro configurável (`use_batch: bool = False`), utilizando modo síncrono por padrão e Batch API da Mistral quando explicitamente ativado.
- Q: Tratamento de falhas de download em projetos individuais → A: Opção A - Registrar o log de erro do projeto afetado e continuar o download dos demais projetos sem interromper a execução.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automate Download of Project PDF Reports (Priority: P1)

As a data analyst or automated ETL pipeline operator, I want the system to automatically connect to the SigPesq portal, locate research projects, and download their official PDF report files into a raw storage directory, so that complete source documents are available for structured data extraction.

**Why this priority**: Downloading the official project PDF documents is the prerequisite first step for any downstream extraction or enrichment. Without raw project PDFs, extraction cannot occur.

**Independent Test**: Can be tested independently by running the PDF download task against valid portal credentials and verifying that PDF files matching project identifiers (e.g. `PJ 6020.pdf`) appear in the designated raw storage directory.

**Acceptance Scenarios**:

1. **Given** valid SigPesq credentials in environment variables, **When** the project download process is executed, **Then** the system logs into the portal, navigates the projects list, and saves project PDF files in `data/raw/sigpesq/projects/`.
2. **Given** previously downloaded project PDFs in the raw storage directory, **When** the download process is run with skip-existing enabled, **Then** already downloaded project PDFs are skipped to avoid redundant downloads.
3. **Given** rate limiting (HTTP 429) or temporary network timeouts during portal navigation, **When** downloading project files, **Then** the system retries with backoff and logs meaningful progress.

---

### User Story 2 - Extract Structured Project Data Using Mistral AI (Priority: P2)

As a data consumer or researcher, I want the system to process downloaded project PDFs using Mistral AI (combining OCR for scanned documents and LLM structured extraction for text), producing validated JSON files containing detailed project metadata (title, objectives, schedule, team, funding), so that project details are standardized and queryable.

**Why this priority**: Transforming unstructured PDF documents into structured JSON datasets unlocks deep analytics, search, and initiative enrichment.

**Independent Test**: Can be tested independently by providing a set of sample project PDFs in raw storage, triggering the extraction component, and verifying that corresponding JSON files containing mandatory project schema fields are written to `data/exports/project_sigpesq_files_json/`.

**Acceptance Scenarios**:

1. **Given** a digital project PDF with native text, **When** the extraction process runs, **Then** text is extracted natively and parsed via Mistral LLM into a validated JSON structure with metadata (`_meta`).
2. **Given** a scanned or image-based project PDF, **When** native text extraction yields insufficient characters, **Then** the system automatically falls back to Mistral OCR to convert document pages to text before JSON extraction.
3. **Given** a batch of project PDFs, **When** batch extraction is enabled, **Then** eligible digital PDFs are submitted via batch API and results are collected into JSON output files upon job completion.

---

### User Story 3 - Integrate Project Extraction with Enrichment Pipeline (Priority: P3)

As an ETL pipeline maintainer, I want the project extraction process to seamlessly integrate with the existing project enrichment flow, so that extracted JSON reports automatically enrich research project initiatives in the database.

**Why this priority**: Completes the end-to-end data pipeline, bridging raw document acquisition, AI extraction, and database persistence.

**Independent Test**: Can be tested independently by triggering the combined workflow on a dataset and verifying that research project records in the database receive updated descriptions, objectives, research lines, and keywords.

**Acceptance Scenarios**:

1. **Given** newly generated project JSON files in the export folder, **When** the enrichment flow runs, **Then** matching research initiatives in the database are updated with rich document fields.
2. **Given** a project JSON that does not match any existing database initiative, **When** `ingest_new` is active, **Then** a new initiative record is created and marked for review.

---

### Edge Cases

- What happens when a project in the portal is a draft and contains no attached files? The system MUST detect empty file listings, log the skip condition cleanly without hanging, and continue to the next project.
- How does the system handle corrupt or unreadable PDF files during extraction? The system MUST record an error entry in the extraction metadata without interrupting the processing of other PDFs in the batch.
- What happens when a single project download fails due to modal or portal timeout? The system MUST log the failure for that specific project, skip it, and continue downloading the remaining projects in the batch.
- What happens when the Mistral API key is missing or invalid? The system MUST perform pre-validation of credentials before starting extraction jobs and fail fast with an actionable error message.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automate browser navigation on the SigPesq portal to locate research projects and download official project PDF documents into `data/raw/sigpesq/projects/`.
- **FR-002**: System MUST support skip-existing behavior to avoid re-downloading project files that already exist on disk.
- **FR-003**: System MUST extract structured data from project PDFs into JSON documents including project code, title, description, keywords, area of knowledge, research line, general and specific objectives, coordinator, team members, start/end dates, schedule items, and funding details.
- **FR-004**: System MUST perform automatic fallback to Optical Character Recognition (OCR) when a project PDF contains scanned images or insufficient native text.
- **FR-005**: System MUST validate all extracted JSON payloads against a formal data schema before writing outputs to `data/exports/project_sigpesq_files_json/`.
- **FR-006**: System MUST attach extraction metadata (`_meta`) to each extracted record, detailing source filename, total pages, extraction timestamp, model identifier, text source (native vs OCR), and list of missing fields.
- **FR-007**: System MUST integrate output JSON files directly into the research project enrichment workflow for initiative database updates.
- **FR-008**: System MUST validate required environment configuration (`SIGPESQ_USERNAME`, `SIGPESQ_PASSWORD`, `MISTRAL_KEY`) before initiating portal navigation or AI API calls.
- **FR-009**: System MUST support a configurable extraction execution mode (`use_batch: bool = False`), using synchronous processing (`ProjectExtractor`) by default and Mistral Batch API (`BatchProjectExtractor`) when batch mode is enabled.

### Key Entities

- **Project PDF Document**: Binary source file retrieved from the SigPesq portal representing a research project submission or summary.
- **Structured Project Report (JSON)**: Standardized schema containing extracted project metadata (objectives, schedule, team, keywords, funding) alongside extraction metadata (`_meta`).
- **Research Initiative**: Database entity representing a research project enriched with structured report fields.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of accessible project PDF files in portal search results are successfully downloaded or skipped if already present.
- **SC-002**: Greater than 95% of valid project PDFs are successfully parsed into valid JSON files without schema validation errors.
- **SC-003**: 100% of scanned/image-only project PDFs are automatically processed via OCR fallback without manual intervention.
- **SC-004**: Extracted JSON reports can be ingested by the enrichment workflow to populate initiative records with zero data loss on mandatory fields.

## Assumptions

- Portal authentication mechanisms and layout structure remain stable during execution.
- A valid Mistral API key with access to OCR and Chat completion endpoints is provided in the environment.
- Local storage has sufficient disk space for temporary PDF storage and JSON export files.
- The `sigpesq_agent` library version specified in project dependencies is installed and accessible.
