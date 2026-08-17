# Contract: Backup Database Merger Interface

## Interface Port (`IBackupDatabaseMerger`)

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path

class IBackupDatabaseMerger(ABC):
    """
    Port defining the interface for merging reference backup SQLite data
    into the active weekly database prior to export.
    """

    @abstractmethod
    def ensure_backup_db(self, backup_db_path: Path, source_archive_path: Optional[Path] = None) -> bool:
        """
        Ensures data/backup/horizon_backup.db exists. If absent, provisions it
        from source_archive_path (novo_backup.zip / export.zip).
        """
        pass

    @abstractmethod
    def merge(self, active_db_path: Path, backup_db_path: Path) -> Dict[str, Any]:
        """
        Merges missing entities and relationships from backup_db_path into active_db_path.
        Returns a summary dictionary with counts of merged entities per table.
        """
        pass

    @abstractmethod
    def sync_backup_from_active(self, active_db_path: Path, backup_db_path: Path) -> bool:
        """
        Updates backup_db_path with active_db_path after a 100% successful weekly run.
        """
        pass
```
