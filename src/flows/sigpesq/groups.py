from typing import Optional

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.core.logic.research_group_loader import ResearchGroupLoader
from src.core.logic.strategies.sigpesq_excel import (
    SigPesqCampusStrategy,
    SigPesqExcelMappingStrategy,
    SigPesqKnowledgeAreaStrategy,
    SigPesqOrganizationStrategy,
    SigPesqResearcherStrategy,
    SigPesqRoleStrategy,
)
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()


@task
def download_groups_task() -> dict:
    """
    Downloads Research Groups from SigPesq and saves to a dedicated folder.
    """
    logger = get_run_logger()
    from agent_sigpesq.strategies import ResearchGroupsDownloadStrategy

    try:
        adapter = SigPesqAdapter(download_dir="data/raw/sigpesq/groups")
        adapter.extract(download_strategies=[ResearchGroupsDownloadStrategy()])
        return {"success": True}
    except Exception as e:
        logger.error(f"Error downloading Research Groups: {e}")
        return {"success": False}


@task
def persist_research_groups():
    """
    Finds the latest Research Group Excel file and loads it into the database.
    """
    logger = get_run_logger()
    import glob
    import os

    # Find latest file
    files = glob.glob("data/raw/sigpesq/groups/research_group/*.xlsx")
    if not files:
        # Fallback to legacy path for compatibility with single-session downloads
        files = glob.glob("data/raw/sigpesq/research_group/*.xlsx")

    if not files:
        logger.warning("No Research Group Excel files found.")
        return

    # Sort by mtime
    latest_file = max(files, key=os.path.getmtime)
    logger.info(f"Loading Research Groups from {latest_file}")

    loader = ResearchGroupLoader(
        mapping_strategy=SigPesqExcelMappingStrategy(),
        org_strategy=SigPesqOrganizationStrategy(),
        campus_strategy=SigPesqCampusStrategy(),
        area_strategy=SigPesqKnowledgeAreaStrategy(),
        researcher_strategy=SigPesqResearcherStrategy(),
        role_strategy=SigPesqRoleStrategy(),
    )
    loader.process_file(latest_file)


@flow(name="Ingest SigPesq Research Groups", **telegram_flow_state_handlers())
def ingest_research_groups_flow() -> None:
    """
    Flow specifically for ingesting Research Groups.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Research Groups Ingestion Flow")

    # Import strategies
    from agent_sigpesq.strategies import ResearchGroupsDownloadStrategy

    adapter = SigPesqAdapter(download_dir="data/raw/sigpesq/groups")

    # 1. Extract Only Groups
    logger.info("Extracting Research Groups...")
    # We ignore the returned raw_data for now as the Loader reads from disk
    adapter.extract(download_strategies=[ResearchGroupsDownloadStrategy()])

    # 2. Persist Groups
    persist_research_groups()

    logger.info("Research Groups Ingestion finished successfully.")


if __name__ == "__main__":
    ingest_research_groups_flow()
