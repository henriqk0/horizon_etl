from typing import Any, Optional

from prefect import flow, get_run_logger

from src.flows.cnpq.groups import sync_cnpq_groups_flow
from src.flows.lattes.complete import lattes_complete_flow
from src.flows.sigpesq.all import ingest_sigpesq_flow
from src.notifications.telegram import telegram_flow_state_handlers


@flow(name="Ingest All Sources", **telegram_flow_state_handlers())
def ingest_all_sources_flow(campus_name: Optional[str] = None) -> dict[str, Any]:
    """
    Run all source ingestion flows sequentially.

    Sources are intentionally separated from export/mart flows so the caller can
    decide whether this run is ingestion-only or a full pipeline with outputs.
    """
    logger = get_run_logger()
    logger.info("Starting all source ingestion flows...")

    sigpesq_result = ingest_sigpesq_flow()
    cnpq_result = sync_cnpq_groups_flow(campus_name=campus_name)
    lattes_result = lattes_complete_flow()

    logger.info("All source ingestion flows finished successfully.")
    return {
        "sources": {
            "sigpesq": sigpesq_result,
            "cnpq": cnpq_result,
            "lattes": lattes_result,
        },
        "warnings": (cnpq_result or {}).get("warnings", []),
    }


if __name__ == "__main__":
    ingest_all_sources_flow()
