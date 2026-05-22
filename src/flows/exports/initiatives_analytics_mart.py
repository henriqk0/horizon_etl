import os

from prefect import flow, get_run_logger, task

from src.core.logic.mart_generator import InitiativeAnalyticsMartGenerator
from src.notifications.telegram import telegram_flow_state_handlers


@task(name="generate_initiative_analytics_mart_task")
def generate_initiative_analytics_mart_task(output_path: str):
    logger = get_run_logger()
    logger.info(
        f"Starting Initiative Analytics Mart generation task to {output_path}..."
    )

    generator = InitiativeAnalyticsMartGenerator()
    generator.generate(output_path)

    logger.info("Initiative Analytics Mart generation task completed.")


@flow(name="Export Initiative Analytics Mart Flow", **telegram_flow_state_handlers())
def export_initiatives_analytics_mart_flow(
    output_path: str = "data/exports/initiatives_analytics_mart.json",
):
    """
    Flow to generate the Initiative Analytics Mart JSON from database.

    Args:
        output_path: Path where the mart JSON will be saved.
    """
    # Ensure absolute path or relative to CWD
    if not os.path.isabs(output_path):
        output_path = os.path.join(os.getcwd(), output_path)

    generate_initiative_analytics_mart_task(output_path)


if __name__ == "__main__":
    export_initiatives_analytics_mart_flow()
