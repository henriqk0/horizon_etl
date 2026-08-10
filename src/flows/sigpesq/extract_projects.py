"""Prefect flow for downloading SigPesq project PDFs, extracting data via Mistral AI, and enriching initiatives."""

from dotenv import load_dotenv
from prefect import flow, get_run_logger

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.adapters.sources.sigpesq.mistral_extractor import SigPesqProjectExtractor
from src.flows.sigpesq.enrich_projects import DEFAULT_PJ_DIR, enrich_projects_flow
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()

DEFAULT_PROJECT_PDF_DIR = "data/raw/sigpesq/projects"


@flow(name="Extract SigPesq Projects Flow", **telegram_flow_state_handlers())
def extract_projects_flow(
    download_dir: str = DEFAULT_PROJECT_PDF_DIR,
    export_dir: str = DEFAULT_PJ_DIR,
    use_batch: bool = False,
    skip_existing: bool = True,
    skip_download: bool = False,
    run_enrichment: bool = True,
) -> dict:
    """
    Orchestrates:
    1. Downloading project PDF files from SigPesq portal using Playwright.
    2. Extracting structured report data via Mistral AI (with OCR fallback).
    3. Delegating to enrich_projects_flow for database initiative enrichment.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Project Extraction Pipeline...")

    stats = {
        "download_dir": download_dir,
        "export_dir": export_dir,
        "use_batch": use_batch,
        "download_success": False,
        "extraction": {"processed": 0, "errors": 0},
        "enrichment_stats": {},
    }

    # Step 1: Download PDFs
    if not skip_download:
        adapter = SigPesqAdapter()
        logger.info(f"Triggering PDF download into {download_dir}...")
        stats["download_success"] = adapter.download_project_pdfs(
            download_dir=download_dir,
            skip_existing=skip_existing,
        )
    else:
        logger.info(f"Skipping PDF download. Using existing files in {download_dir}.")
        stats["download_success"] = True

    # Step 2: Extract structured JSONs using Mistral AI
    extractor = SigPesqProjectExtractor()
    logger.info(f"Starting Mistral AI extraction (use_batch={use_batch})...")
    extraction_result = extractor.process_directory(
        pdf_dir=download_dir,
        output_dir=export_dir,
        use_batch=use_batch,
    )
    stats["extraction"] = extraction_result

    # Step 3: Trigger enrichment flow
    if run_enrichment:
        logger.info("Triggering project enrichment flow...")
        enrichment_result = enrich_projects_flow(pj_dir=export_dir)
        stats["enrichment_stats"] = enrichment_result

    logger.info(f"Extract SigPesq Projects Flow finished: {stats}")
    return stats


if __name__ == "__main__":
    extract_projects_flow()
