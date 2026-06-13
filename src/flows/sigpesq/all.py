from dotenv import load_dotenv
from prefect import flow, get_run_logger

from src.flows.sigpesq.groups import (
    download_sigpesq_category,
    ingest_advisorships_flow,
    ingest_projects_flow,
    ingest_research_groups_flow,
    persist_advisorships,
    persist_projects,
    persist_research_groups,
)
from src.notifications.telegram import telegram_flow_state_handlers

load_dotenv()


def download_all_sigpesq_reports() -> None:
    from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
    from agent_sigpesq.strategies import (
        ResearchGroupsDownloadStrategy,
        ProjectsDownloadStrategy,
        AdvisorshipsDownloadStrategy,
    )
    adapter = SigPesqAdapter()
    adapter.extract(
        download_strategies=[
            ResearchGroupsDownloadStrategy(),
            ProjectsDownloadStrategy(),
            AdvisorshipsDownloadStrategy(),
        ]
    )


@flow(name="Ingest SigPesq Full", **telegram_flow_state_handlers())
def ingest_sigpesq_flow() -> None:
    """
    Main Prefect Flow for ingesting ALL SigPesq data.

    Downloads all reports sequentially (using existing individual flows),
    then persists each dataset.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Full Ingestion Flow")

    # Legacy sequential flow - runs each extraction/persistence in order
    ingest_research_groups_flow()
    ingest_projects_flow()
    ingest_advisorships_flow()

    logger.info("Flow finished successfully.")


@flow(name="Ingest SigPesq Full (Parallel Download)", **telegram_flow_state_handlers())
def ingest_sigpesq_parallel_flow() -> None:
    """
    Prefect flow that downloads all SigPesq reports in PARALLEL, then persists sequentially.

    Strategy:
    1. Parallel downloads of SigPesq data using .map() (I/O-bound, network requests)
    2. Sequential persistence to DB (to avoid SQLite lock issues)
    """
    logger = get_run_logger()
    logger.info("Starting SigPesq Parallel Download Flow")

    # Step 1: Parallel downloads using .map()
    logger.info("Downloading all SigPesq reports in parallel...")
    categories = ["groups", "projects", "advisorships"]
    download_results = download_sigpesq_category.map(categories)

    # Step 2: Sequential persistence (check success before proceeding)
    logger.info("Persisting data to database (sequential)...")

    # Groups persistence
    groups_result = download_results[0]
    if groups_result.get("success"):
        persist_research_groups()
    else:
        logger.warning(
            f"Skipping groups persistence due to download failure: {groups_result.get('error')}"
        )

    # Projects persistence
    projects_result = download_results[1]
    if projects_result.get("success"):
        persist_projects()
    else:
        logger.warning(
            f"Skipping projects persistence due to download failure: {projects_result.get('error')}"
        )

    # Advisorships persistence
    advisorships_result = download_results[2]
    if advisorships_result.get("success"):
        persist_advisorships()
    else:
        logger.warning(
            f"Skipping advisorships persistence due to download failure: {advisorships_result.get('error')}"
        )

    logger.info("SigPesq Parallel Flow finished successfully.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "projects":
            ingest_projects_flow()
        elif command == "groups":
            ingest_research_groups_flow()
        elif command == "advisorships":
            ingest_advisorships_flow()
        elif command == "parallel":
            ingest_sigpesq_parallel_flow()
        else:
            print(f"Unknown command: {command}. Running Full Flow.")
            ingest_sigpesq_flow()
    else:
        print(
            "Running Full Flow (Default). usage: python all.py [projects|groups|advisorships|parallel]"
        )
        ingest_sigpesq_flow()