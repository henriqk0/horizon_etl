# Research & Architectural Decisions: Per-Phase ZIP Fallback Seeding & Data Provenance Reporting

## Technical Decisions

### 1. Inter-Process Provenance Tracking Architecture

- **Decision**: Use lightweight file-based provenance markers in `data/exports/` (e.g. `.sigpesq_provenance`, `.cnpq_provenance`, `.lattes_provenance`) created by each adapter or flow during execution. Read these markers in `weekly_orchestrator._run_phase()` to attach `"origin"` (`"LIVE"`, `"ZIP ANTERIOR"`, `"PARCIAL"`, or `"VAZIO"`) to the phase result dictionary.
- **Rationale**: `weekly_orchestrator.py` executes each phase in an isolated `subprocess.run(["python", ...])`. Environment variables do not pass backward from child processes to parent processes, but marker files written to disk are reliably readable by the parent orchestrator after process termination.

### 2. Canonical Database Seeder (`CanonicalDatabaseSeeder`)

- **Decision**: Create `src/core/logic/canonical_database_seeder.py` to parse canonical JSON artifacts (`data/exports/research_groups_canonical.json`, `researchers_canonical.json`) and seed SQLite tables (`research_groups`, `researchers`) if table counts are zero before running source synchronization tasks.
- **Rationale**: Fully adheres to Constitution Principle I (Ports & Adapters) and Principle II (Domain-First Data Modeling). Solves empty-table execution issues in `cnpq_sync` when live SigPesq download is offline.

### 3. Summary Table & Notification Formatting

- **Decision**: Expand `weekly_orchestrator.py` summary table formatting width to accommodate the provenance tag `[LIVE]`, `[ZIP ANTERIOR]`, `[PARCIAL]`, or `[VAZIO]` on every step row. Pass the provenance tags to `_notify()` for Telegram message formatting.
- **Rationale**: Provides clear visual indication of data freshness without cluttering logs.
