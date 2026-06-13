import glob
import os
import shutil
from typing import Optional

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.core.logic.research_group_loader import ResearchGroupLoader
from src.core.logic.project_loader import ProjectLoader
from src.core.logic.strategies.sigpesq_excel import (
    SigPesqCampusStrategy,
    SigPesqExcelMappingStrategy,
    SigPesqKnowledgeAreaStrategy,
    SigPesqOrganizationStrategy,
    SigPesqResearcherStrategy,
    SigPesqRoleStrategy,
)
from src.core.logic.strategies.sigpesq_projects import SigPesqProjectMappingStrategy
from src.core.logic.strategies.sigpesq_advisorships import SigPesqAdvisorshipMappingStrategy
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()

# Mapping of category names to their download strategies
_SIGPESQ_CATEGORY_STRATEGY_MAP = {
    "groups": "ResearchGroupsDownloadStrategy",
    "projects": "ProjectsDownloadStrategy",
    "advisorships": "AdvisorshipsDownloadStrategy",
}

# Mapping of category names to their subdirectories in downloaded files
_SIGPESQ_CATEGORY_SUBDIR_MAP = {
    "groups": "research_group",
    "projects": "research_projects",
    "advisorships": "advisorships",
}


@task
def download_sigpesq_category(category: str) -> dict:
    """
    Downloads a specific SigPesq category (I/O-bound - can run in parallel).

    Args:
        category: One of 'groups', 'projects', 'advisorships'

    Returns:
        dict with success status, download_dir, category, and error if any
    """
    logger = get_run_logger()
    logger.info(f"Downloading SigPesq category: {category}")

    # Import the appropriate strategy
    from agent_sigpesq.strategies import (
        AdvisorshipsDownloadStrategy,
        ProjectsDownloadStrategy,
        ResearchGroupsDownloadStrategy,
    )

    strategy_map = {
        "groups": ResearchGroupsDownloadStrategy,
        "projects": ProjectsDownloadStrategy,
        "advisorships": AdvisorshipsDownloadStrategy,
    }

    if category not in strategy_map:
        logger.error(f"Unknown SigPesq category: {category}")
        return {"success": False, "category": category, "error": f"Unknown category: {category}"}

    strategy_class = strategy_map[category]

    # Create a dedicated download directory for this category
    download_dir = f"data/raw/sigpesq_download_{category}"
    if os.path.exists(download_dir):
        shutil.rmtree(download_dir)
    os.makedirs(download_dir, exist_ok=True)

    adapter = SigPesqAdapter(download_dir=download_dir)

    try:
        adapter.extract(download_strategies=[strategy_class()])
        logger.info(f"{category.capitalize()} download completed.")
        return {"success": True, "download_dir": download_dir, "category": category}
    except Exception as e:
        logger.error(f"Failed to download {category}: {e}")
        return {"success": False, "download_dir": download_dir, "category": category, "error": str(e)}


@task
def persist_research_groups():
    """
    Finds the latest Research Group Excel file and loads it into the database.
    """
    logger = get_run_logger()

    # Find latest file - check multiple possible locations
    files = glob.glob("data/raw/sigpesq*/research_group/*.xlsx", recursive=True)
    if not files:
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


@task
def persist_projects():
    """
    Finds the latest Projects Excel file and loads it into the database.
    """
    logger = get_run_logger()

    # Find latest file - check multiple possible locations
    files = glob.glob("data/raw/sigpesq*/research_projects/*.xlsx", recursive=True)
    if not files:
        files = glob.glob("data/raw/sigpesq/research_projects/*.xlsx")

    if not files:
        logger.warning(
            "No Project Excel files found in data/raw/sigpesq*/research_projects/."
        )
        return

    # Sort by mtime
    latest_file = max(files, key=os.path.getmtime)
    logger.info(f"Loading Projects from {latest_file}")

    loader = ProjectLoader(mapping_strategy=SigPesqProjectMappingStrategy())
    loader.process_file(latest_file)


@task
def persist_advisorships():
    """
    Finds the latest Advisorships Excel file and loads it into the database.
    """
    logger = get_run_logger()

    # Find latest file - check multiple possible locations
    files = glob.glob("data/raw/sigpesq*/advisorships/**/*.xlsx", recursive=True)
    if not files:
        files = glob.glob("data/raw/sigpesq/advisorships/**/*.xlsx", recursive=True)

    if not files:
        # Try generic sigpesq folder if specific one doesn't exist
        files = glob.glob("data/raw/sigpesq*.xlsx")

    if not files:
        logger.warning("No Advisorship Excel files found.")
        return

    # Sort by mtime (optional, but good for logs)
    files.sort(key=os.path.getmtime)

    loader = ProjectLoader(mapping_strategy=SigPesqAdvisorshipMappingStrategy())

    # Ensure "Advisorship" initiative type exists once
    existing_types = loader.controller.list_initiative_types()
    raw_type = next(
        (
            t
            for t in existing_types
            if (t.get("name") if isinstance(t, dict) else getattr(t, "name", ""))
            == "Advisorship"
        ),
        None,
    )

    if not raw_type:
        logger.info("Creating 'Advisorship' initiative type...")
        raw_type = loader.controller.create_initiative_type(
            name="Advisorship", description="Bolsas e Orientações importadas do SigPesq"
        )

    # Wrap in object if it's a dict (ProjectLoader expects .id)
    if isinstance(raw_type, dict):

        class Obj:
            pass

        loader.initiative_type = Obj()
        loader.initiative_type.id = raw_type.get("id")
        loader.initiative_type.name = raw_type.get("name")
    else:
        loader.initiative_type = raw_type

    for file_path in files:
        logger.info(f"Loading Advisorships from {file_path}")
        loader.process_file(file_path)

    # Final pass: Recalculate parent project dates and status from DB
    loader.recalculate_all_parent_statuses()


# Legacy flow functions for backward compatibility
@flow(name="Ingest SigPesq Research Groups", **telegram_flow_state_handlers())
def ingest_research_groups_flow() -> None:
    """
    Flow specifically for ingesting Research Groups.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Research Groups Ingestion Flow")

    # 1. Extract Only Groups
    logger.info("Extracting Research Groups...")
    from agent_sigpesq.strategies import ResearchGroupsDownloadStrategy

    adapter = SigPesqAdapter()
    adapter.extract(download_strategies=[ResearchGroupsDownloadStrategy()])

    # 2. Persist Groups
    persist_research_groups()

    logger.info("Research Groups Ingestion finished successfully.")


@flow(name="Ingest SigPesq Projects", **telegram_flow_state_handlers())
def ingest_projects_flow() -> None:
    """
    Prefect flow for ingesting Research Projects (Initiatives) from SigPesq.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Projects Ingestion Flow")

    # 1. Extract Only Projects
    logger.info("Extracting Projects...")
    from agent_sigpesq.strategies import ProjectsDownloadStrategy

    adapter = SigPesqAdapter()
    adapter.extract(download_strategies=[ProjectsDownloadStrategy()])

    # 2. Persist Projects
    persist_projects()

    logger.info("Projects Ingestion finished successfully.")


@flow(name="Ingest SigPesq Advisorships", **telegram_flow_state_handlers())
def ingest_advisorships_flow() -> None:
    """
    Prefect flow for ingesting Advisorships (Bolsistas) from SigPesq.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Advisorships Ingestion Flow")

    from agent_sigpesq.strategies import AdvisorshipsDownloadStrategy

    adapter = SigPesqAdapter()

    # 1. Extract Advisorships
    logger.info("Extracting Advisorships...")
    adapter.extract(download_strategies=[AdvisorshipsDownloadStrategy()])

    # 2. Persist Advisorships
    persist_advisorships()

    logger.info("Advisorships Ingestion finished successfully.")


if __name__ == "__main__":
    # Default to running individual flows sequentially for backward compatibility
    ingest_research_groups_flow()