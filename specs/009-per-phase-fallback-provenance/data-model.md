# Data Model & Domain Entities: Per-Phase Fallback Seeding & Data Provenance

## Transient Structures

### 1. PhaseProvenance

Represents the execution outcome and data provenance of an individual pipeline phase.

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `name` | `str` | Name of the pipeline phase (e.g., `sigpesq`, `cnpq`, `export_zip`). |
| `ok` | `bool` | `True` if phase completed with exit code 0. |
| `rc` | `int \| None` | Subprocess return code or `None` on timeout. |
| `critical` | `bool` | Whether failure in this phase is fatal to overall pipeline exit code. |
| `elapsed` | `float` | Duration of phase execution in seconds. |
| `origin` | `str` | Data provenance: `"LIVE"`, `"ZIP ANTERIOR"`, `"PARCIAL"`, or `"VAZIO"`. |

## Database Seeding Schemas

### Research Groups Seeding (`data/exports/research_groups_canonical.json` → `research_groups`)

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `int` | Research group ID. |
| `name` | `str` | Name of the research group. |
| `cnpq_url` | `str` | Mirror URL used for CNPq group synchronization. |
| `campus_id` | `int` | Associated campus ID. |
