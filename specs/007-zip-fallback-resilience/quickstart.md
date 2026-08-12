# Quickstart: Testing ZIP Fallback & Data Resilience

## Quick Verification

### 1. Test Resilient ZIP Creation CLI
To verify that `scripts/export_zip.py` creates a ZIP archive without unlinking on missing optional subgraphs:

```bash
.venv/bin/python scripts/export_zip.py data/exports --dry-run
```

### 2. Test Prefect Export Flow
To test canonical export generation and ZIP packaging:

```bash
make export-canonical
```

### 3. Verify ZIP Contents
Check that `data/exports/exports_canonical.zip` is created and contains the project JSONs:

```bash
unzip -l data/exports/exports_canonical.zip | grep project_sigpesq_files_json | head -5
```
