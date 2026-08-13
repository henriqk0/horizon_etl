# Component & Flow Contracts: Per-Phase Fallback Seeding & Data Provenance

## Core Logic Contracts

### 1. `CanonicalDatabaseSeeder` (`src/core/logic/canonical_database_seeder.py`)

```python
class CanonicalDatabaseSeeder:
    """
    Seeds SQLite database tables (horizon.db) from canonical export JSONs
    when live ingestion sources are unavailable or returned zero items.
    """

    def seed_research_groups_if_empty(
        self, export_dir: str = "data/exports"
    ) -> int:
        """
        If research_groups table in horizon.db is empty, parses
        research_groups_canonical.json from export_dir and populates DB.
        Returns count of seeded research groups.
        """
        ...
```

### 2. Provenance Marker API (`src/core/logic/provenance_tracker.py`)

```python
class ProvenanceTracker:
    """
    Manages reading and writing data origin marker files in data/exports/.
    """

    @staticmethod
    def set_provenance(phase_name: str, origin: str, export_dir: str = "data/exports") -> None:
        """
        Writes .<phase_name>_provenance file containing origin ('LIVE', 'ZIP ANTERIOR', 'PARCIAL', 'VAZIO').
        """
        ...

    @staticmethod
    def get_provenance(phase_name: str, export_dir: str = "data/exports") -> str:
        """
        Reads .<phase_name>_provenance file. Returns origin or default 'LIVE'.
        """
        ...
```

## CLI Summary Output Contract

```text
========================================================
  Weekly pipelines — Summary
========================================================
  Step  1  ✓  sigpesq................... [LIVE]        13.8s
  Step  2  ⚠  cnpq...................... [ZIP ANTERIOR] 2.8s
  Step  3  ✓  lattes_download........... [LIVE]        11.8s
```
