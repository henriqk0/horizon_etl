# Quickstart Guide: SigPesq PDF Download & Mistral Report Extraction

**Feature Branch**: `006-sigpesq-pdf-mistral-extraction`  
**Date**: 2026-08-10  

## Prerequisites

1. Set required environment variables in `.env`:
   ```bash
   SIGPESQ_USERNAME="seu_usuario"
   SIGPESQ_PASSWORD="sua_senha"
   MISTRAL_KEY="sua_chave_mistral"
   ```

2. Ensure dependencies are installed in virtual environment:
   ```bash
   make setup
   ```

## Running the Prefect Flow

### Option A: Run via Python CLI / Flow Script

To execute the complete download, Mistral AI extraction, and initiative enrichment pipeline:

```bash
poetry run python -m src.flows.sigpesq.extract_projects
```

Parameters supported:
- `download_dir` (default: `"data/raw/sigpesq/projects"`): Directory to store raw PDFs.
- `export_dir` (default: `"data/exports/project_sigpesq_files_json"`): Directory to save extracted JSON reports.
- `use_batch` (default: `False`): Set to `True` to use Mistral Batch API for digital PDFs.
- `skip_existing` (default: `True`): Skip re-downloading PDFs that already exist on disk.
- `run_enrichment` (default: `True`): Automatically trigger `enrich_projects_flow` after extraction.

### Option B: Run via Makefile / CLI Target

```bash
make etl-sigpesq-projects
```

## Running Tests

To run unit and integration tests for the project extraction component:

```bash
poetry run pytest tests/test_sigpesq_project_extraction.py
```
