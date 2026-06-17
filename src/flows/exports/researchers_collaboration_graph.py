import os

from prefect import flow, get_run_logger, task

from src.core.logic.researchers_collaboration_graph_generator import (
    ResearchersCollaborationGraphGenerator,
)
from src.notifications.telegram import telegram_flow_state_handlers


@task(name="generate_researchers_collaboration_graph_task")
def generate_researchers_collaboration_graph_task(output_dir: str):
    logger = get_run_logger()
    output_path = os.path.join(output_dir, "researchers_only_collaboration_graph.json")
    logger.info("Generating Researchers Collaboration Graph → %s", output_path)

    generator = ResearchersCollaborationGraphGenerator()
    result = generator.generate(
        researchers_path=os.path.join(output_dir, "researchers_canonical.json"),
        output_path=output_path,
    )

    logger.info(
        "Researchers Collaboration Graph completed: %d nodes, %d edges.",
        result["graph_stats"]["nodes"],
        result["graph_stats"]["edges"],
    )


@flow(
    name="Export Researchers Collaboration Graph Flow", **telegram_flow_state_handlers()
)
def export_researchers_collaboration_graph_flow(output_dir: str = "data/exports"):
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.getcwd(), output_dir)

    generate_researchers_collaboration_graph_task(output_dir)


if __name__ == "__main__":
    export_researchers_collaboration_graph_flow()
