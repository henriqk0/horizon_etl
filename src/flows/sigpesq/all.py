from agent_sigpesq.strategies import (
    AdvisorshipsDownloadStrategy,
    ProjectsDownloadStrategy,
    ResearchGroupsDownloadStrategy,
)
from dotenv import load_dotenv
from prefect import flow, get_run_logger

from src.adapters.sources.sigpesq.adapter import SigPesqAdapter
from src.flows.sigpesq.advisorships import (
    ingest_advisorships_flow,
    persist_advisorships,
)
from src.flows.sigpesq.groups import (
    ingest_research_groups_flow,
    persist_research_groups,
)
from src.flows.sigpesq.projects import ingest_projects_flow, persist_projects
from src.notifications.telegram import telegram_flow_state_handlers
from src.tracking.recorder import tracking_recorder

load_dotenv()


def _download_strategies():
    return [
        ResearchGroupsDownloadStrategy(),
        ProjectsDownloadStrategy(),
        AdvisorshipsDownloadStrategy(),
    ]


def download_all_sigpesq_reports() -> None:
    """Download all SigPesq reports using a single login session (no persist)."""
    adapter = SigPesqAdapter()
    adapter.extract(download_strategies=_download_strategies())


@flow(name="Ingest SigPesq Full", **telegram_flow_state_handlers())
def ingest_sigpesq_flow() -> None:
    """
    Main Prefect Flow for ingesting ALL SigPesq data.
    Downloads all reports using a single SigPesq login, then persists each dataset.
    """
    logger = get_run_logger()
    logger.info("Initializing SigPesq Full Ingestion Flow")

    with tracking_recorder.run_context(source_system="sigpesq", flow_name="ingest_sigpesq_full"):
        adapter = SigPesqAdapter()
        logger.info("Extracting all SigPesq reports with a single login...")
        adapter.extract(download_strategies=_download_strategies())

        logger.info("Persisting SigPesq research groups...")
        persist_research_groups()

        logger.info("Persisting SigPesq projects...")
        persist_projects()

        logger.info("Persisting SigPesq advisorships...")
        persist_advisorships()

        logger.info("Flow finished successfully.")


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
        else:
            print(f"Unknown command: {command}. Running Full Flow.")
            ingest_sigpesq_flow()
    else:
        print(
            "Running Full Flow (Default). usage: python ingest_sigpesq.py [projects|groups]"
        )
        ingest_sigpesq_flow()
