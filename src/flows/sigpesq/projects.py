from typing import Optional

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.core.logic.project_loader import ProjectLoader
from src.core.logic.strategies.sigpesq_projects import SigPesqProjectMappingStrategy
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()


@task
def download_projects_task() -> dict:
    """
    Downloads Research Projects from SigPesq and saves to a dedicated folder.
    """
    logger = get_run_logger()
    from agent_sigpesq.strategies import ProjectsDownloadStrategy

    try:
        adapter = SigPesqAdapter(download_dir="data/raw/sigpesq/projects")
        adapter.extract(download_strategies=[ProjectsDownloadStrategy()])
        return {"success": True}
    except Exception as e:
        logger.error(f"Error downloading Research Projects: {e}")
        return {"success": False}


@task
def persist_projects():
    """
    Finds the latest Projects Excel file and loads it into the database.

    This task identifies the most recent file in the raw SigPesq data directory,
    initializes a ProjectLoader with the SigPesq mapping strategy, and processes
     the file to persist initiatives and their respective teams.
    """
    logger = get_run_logger()
    import glob
    import os

    # Find latest file
    files = glob.glob("data/raw/sigpesq/projects/research_projects/*.xlsx")
    if not files:
        # Fallback to legacy path for compatibility with single-session downloads
        files = glob.glob("data/raw/sigpesq/research_projects/*.xlsx")

    if not files:
        logger.warning(
            "No Project Excel files found in data/raw/sigpesq/projects/research_projects/ or legacy folder."
        )
        return

    # Sort by mtime
    latest_file = max(files, key=os.path.getmtime)
    logger.info(f"Loading Projects from {latest_file}")

    loader = ProjectLoader(mapping_strategy=SigPesqProjectMappingStrategy())
    loader.process_file(latest_file)


@flow(name="Ingest SigPesq Projects", **telegram_flow_state_handlers())
def ingest_projects_flow() -> None:
    """
    Prefect flow for ingesting Research Projects (Initiatives) from SigPesq.

    This flow performs the extraction of project data from the SigPesq data source
    using an adapter and then triggers the persist_projects task to load the
    extracted data into the canonical database.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Projects Ingestion Flow")

    # Import strategies
    from agent_sigpesq.strategies import ProjectsDownloadStrategy

    adapter = SigPesqAdapter(download_dir="data/raw/sigpesq/projects")

    # 1. Extract Only Projects
    logger.info("Extracting Projects...")
    adapter.extract(download_strategies=[ProjectsDownloadStrategy()])

    # 2. Persist Projects
    persist_projects()

    logger.info("Projects Ingestion finished successfully.")


if __name__ == "__main__":
    ingest_projects_flow()
