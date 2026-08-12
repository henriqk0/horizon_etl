# Component & Flow Contracts: Export ZIP Cache Bootstrapping

## Core Logic Contract

### `ExportCacheBootstrapper` (`src/core/logic/export_cache_bootstrapper.py`)

```python
class ExportCacheBootstrapper:
    """
    Discovers the most recent export ZIP archive and extracts its contents
    into target export directory prior to ingestion pipeline execution.
    """

    def find_latest_archive(
        self, search_dirs: list[str] = None
    ) -> Path | None:
        """
        Scans search_dirs (default: ['data/exports', '.']) for matching archives
        ('canonical_export_*.zip', 'exports_canonical.zip'). Returns Path to newest
        file by mtime, or None if none found.
        """
        ...

    def bootstrap(
        self,
        target_dir: str = "data/exports",
        search_dirs: list[str] = None,
    ) -> dict[str, Any]:
        """
        Finds and extracts the latest archive into target_dir. Retains source ZIP.
        Returns summary dictionary with keys: restored (bool), archive_used (str),
        files_extracted (int), warning (str|None).
        """
        ...
```

## Prefect Task Contract

### `bootstrap_export_cache_task` (`src/flows/exports/canonical_data.py`)

```python
@task(name="bootstrap_export_cache_task")
def bootstrap_export_cache_task(
    target_dir: str = "data/exports",
) -> dict[str, Any]:
    """
    Prefect wrapper task that triggers ExportCacheBootstrapper.bootstrap().
    Logs info/warning messages to Prefect logger.
    """
    ...
```

## CLI / Script Usage

```bash
# Direct Python execution via app.py or orchestrator
python -c "from src.core.logic.export_cache_bootstrapper import ExportCacheBootstrapper; ExportCacheBootstrapper().bootstrap()"
```
