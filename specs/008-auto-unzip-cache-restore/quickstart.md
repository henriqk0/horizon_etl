# Quickstart Verification: Automated Export ZIP Extraction & Cache Bootstrapping

## Prerequisites

Ensure python virtualenv is active:
```bash
source .venv/bin/activate
```

## Quick Verification Steps

### 1. Test Discovery & Unpacking with Mock Export ZIP

```bash
# Run unit test suite
PYTHONPATH=. .venv/bin/pytest tests/test_auto_unzip_bootstrap.py
```

### 2. Verify Manual Root ZIP Restoration

```bash
# Ensure a ZIP is in root or data/exports/
ls -lh canonical_export_*.zip data/exports/canonical_export_*.zip 2>/dev/null || true

# Test bootstrap execution
.venv/bin/python -c "
from src.core.logic.export_cache_bootstrapper import ExportCacheBootstrapper
res = ExportCacheBootstrapper().bootstrap()
print('Bootstrap Result:', res)
"
```

### 3. Verify Full Pipeline Execution

```bash
# Execute weekly flow pipeline
make weekly-flows
```
