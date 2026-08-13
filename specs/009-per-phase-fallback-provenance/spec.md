# Feature Specification: Per-Phase ZIP Fallback Seeding & Data Provenance Reporting

**Feature Branch**: `009-per-phase-fallback-provenance`

**Created**: 2026-08-13

**Status**: Draft

**Input**: User description: "/speckit-specify Implementar fallback de dados por etapa a partir de ZIPs anteriores com exibição da origem no resumo final"

## Clarifications

### Session 2026-08-13

- Q: Qual formato de rótulo de proveniência deve ser exibido na tabela final de resumo? → A: Usar `[LIVE]` (dados novos), `[ZIP ANTERIOR]` (fallback), `[PARCIAL]` (misto), `[VAZIO]` (0 itens).
- Q: Quais arquivos canônicos devem ser carregados para popular o banco de dados (seed) em caso de fallback? → A: Popular `research_groups_canonical.json` (grupos do CNPq) e tabelas associadas conforme necessário por cada etapa.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transparent Provenance in Final Summary Table (Priority: P1) 🎯 MVP

As a pipeline operator viewing the execution summary table of `make weekly-flows`, I see an explicit data provenance tag (`[LIVE]` vs `[ZIP ANTERIOR]` vs `[PARCIAL]` vs `[VAZIO]`) alongside every executed pipeline phase, so that I immediately know which data sources were updated live versus which relied on fallback data from prior export archives.

**Why this priority**: Delivers immediate visibility and transparency to operators regarding data freshness without digging into execution log files.

**Independent Test**: Run orchestrator where one step succeeds live and another fails over to cached ZIP data, verifying the final summary table displays `[LIVE]` and `[ZIP ANTERIOR]` tags for the respective steps.

**Acceptance Scenarios**:

1. **Given** a successful live source execution for a step (e.g., `lattes_download`), **When** the summary table is printed at pipeline completion, **Then** the step row includes the `[LIVE]` provenance tag.
2. **Given** an offline/unreachable source execution that falls back to prior ZIP data (e.g., `cnpq`), **When** the summary table is printed, **Then** the step row includes the `[ZIP ANTERIOR]` provenance tag.
3. **Given** Telegram state notifications are enabled, **When** flow completion notifications are sent, **Then** the message body includes the provenance tag for each phase.

---

### User Story 2 - Per-Phase Database Seeding on Source Unavailability (Priority: P2)

As an automated ETL pipeline, when any individual source step (SigPesq, CNPq, Lattes) is unable to connect to its live portal or returns zero live items due to network downtime, the system automatically seeds its required database entities (such as research group URLs from `research_groups_canonical.json` into `horizon.db`) from previously decompressed export ZIP artifacts so downstream steps execute with complete database context instead of running against empty tables.

**Why this priority**: Prevents cascading empty-state execution in downstream steps (e.g. `cnpq` group sync skipping when research groups were not downloaded live in `sigpesq`).

**Independent Test**: Simulate offline SigPesq execution with pre-existing `research_groups_canonical.json` in `data/exports/`, verify database is populated with research groups, and run `cnpq_sync` to confirm it processes the seeded groups instead of returning 0 items in 2.8 seconds.

**Acceptance Scenarios**:

1. **Given** an empty `research_groups` database table and an offline SigPesq portal, **When** `get_groups_to_sync` or phase initialization runs, **Then** the system automatically seeds `research_groups` from `data/exports/research_groups_canonical.json` (or latest export ZIP).
2. **Given** the database is seeded from prior export artifacts, **When** `cnpq` group synchronization executes, **Then** it processes all seeded group URLs and marks step provenance as `[ZIP ANTERIOR]`.

---

### Edge Cases

- What happens when a phase is partly live and partly fallback? The system MUST mark the phase provenance as `[PARCIAL]` if both live items and fallback items were processed.
- What happens if no prior ZIP artifact exists and live portal is offline? The system MUST mark provenance as `[VAZIO]`, log an info message, and proceed without raising unhandled exceptions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST record execution provenance (`LIVE`, `ZIP ANTERIOR`, `PARCIAL`, or `VAZIO`) for every phase in the weekly pipeline.
- **FR-002**: System MUST render the execution provenance tag (`[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, `[VAZIO]`) in the final CLI summary table printed by `weekly_orchestrator`.
- **FR-003**: System MUST include the provenance tag per phase in Telegram completion notifications.
- **FR-004**: System MUST provide database seeding capabilities from canonical export artifacts (`data/exports/*.json`) when live source steps are unable to fetch raw data.
- **FR-005**: `cnpq_sync` MUST check for canonical research group export artifacts (`research_groups_canonical.json`) to seed the database if the `research_groups` table contains 0 entries.
- **FR-006**: System MUST NOT overwrite live-updated database records with older export artifacts when live data is successfully fetched.

### Key Entities *(include if feature involves data)*

- **Phase Execution Provenance**: Tracking entity recording `phase_name`, `status_ok`, `elapsed_seconds`, and `data_origin` (`LIVE`, `ZIP_FALLBACK`, `HYBRID`, `EMPTY`).
- **Database Seed Exporter/Loader**: Helper responsible for loading canonical export JSON files into SQLite tables when live ingestion is unavailable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pipeline phases in `Weekly pipelines — Summary` display their data origin tag (`[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, or `[VAZIO]`).
- **SC-002**: CNPq synchronization executes against 100% of seeded research groups when SigPesq live download is offline but prior export JSONs exist.
- **SC-003**: Provenance tracking adds less than 1 second of overhead to the total pipeline run time.

## Assumptions

- Prior export JSON artifacts in `data/exports/` follow canonical domain schemas.
- `weekly_orchestrator` process-isolated subprocesses return structured exit metadata including data provenance.
