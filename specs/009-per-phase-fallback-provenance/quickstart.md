# Quickstart Verification: Per-Phase Fallback Seeding & Data Provenance

## Prerequisites

Ensure python virtualenv is active:
```bash
source .venv/bin/activate
```

## Quick Verification Steps

### 1. Test Unit Suite for Seeder & Provenance

```bash
# Run unit test suite
PYTHONPATH=. .venv/bin/pytest tests/test_provenance_and_seeder.py
```

### 2. Verify Database Seeding from Canonical JSON

```bash
# Run database seeder test
.venv/bin/python -c "
from src.core.logic.canonical_database_seeder import CanonicalDatabaseSeeder
count = CanonicalDatabaseSeeder().seed_research_groups_if_empty()
print('Seeded research groups:', count)
"
```

### 3. Verify Provenance Tag Output in Orchestrator

```bash
# Run full weekly pipelines to observe summary table tags
make weekly-flows
```
