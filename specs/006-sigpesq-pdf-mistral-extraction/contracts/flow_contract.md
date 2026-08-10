# Interface Contract: SigPesq Project Extraction Flow

**Feature Branch**: `006-sigpesq-pdf-mistral-extraction`  
**Date**: 2026-08-10  

## Prefect Flow Signature

```python
@flow(name="Extract SigPesq Projects Flow", **telegram_flow_state_handlers())
def extract_projects_flow(
    download_dir: str = "data/raw/sigpesq/projects",
    export_dir: str = "data/exports/project_sigpesq_files_json",
    use_batch: bool = False,
    skip_existing: bool = True,
    run_enrichment: bool = True,
) -> dict:
    """
    Orchestrates downloading project PDF files from SigPesq, performing Mistral AI
    structured extraction (with OCR fallback), writing JSON export files, and optionally
    triggering initiative database enrichment.
    """
```

## Input Environment Variables

| Variable | Required | Description |
| :--- | :--- | :--- |
| `SIGPESQ_USERNAME` / `SIGPESQ_USER` | Yes | Portal username for SigPesq login |
| `SIGPESQ_PASSWORD` | Yes | Portal password for SigPesq login |
| `MISTRAL_KEY` / `MISTRAL_API_KEY` | Yes | API key for Mistral AI OCR & Chat models |

## Flow Return Value

Returns a summary dictionary:

```python
{
    "downloaded_pdfs": 42,
    "extracted_jsons": 42,
    "ocr_fallbacks": 3,
    "batch_jobs": 0,
    "enrichment_stats": {
        "matched": 38,
        "created": 4,
        "needs_review": 4
    }
}
```
