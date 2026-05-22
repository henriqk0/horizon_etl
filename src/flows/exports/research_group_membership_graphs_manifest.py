import os

from prefect import flow, get_run_logger, task

from src.core.logic.research_group_membership_graphs_manifest_generator import (
    ResearchGroupMembershipGraphsManifestGenerator,
)
from src.notifications.telegram import telegram_flow_state_handlers


@task(name="generate_research_group_membership_graphs_manifest_task")
def generate_research_group_membership_graphs_manifest_task(output_dir: str):
    logger = get_run_logger()
    output_path = os.path.join(
        output_dir, "research_group_membership_graphs_manifest.json"
    )
    logger.info(
        "Generating Research Group Membership Graphs Manifest → %s", output_path
    )

    generator = ResearchGroupMembershipGraphsManifestGenerator()
    result = generator.generate(output_dir=output_dir, output_path=output_path)

    meta = result["metadata"]
    logger.info(
        "Manifest completed: %d groups, %d total nodes, %d total edges.",
        meta["total_groups"],
        meta["total_nodes"],
        meta["total_edges"],
    )


@flow(
    name="Export Research Group Membership Graphs Manifest Flow",
    **telegram_flow_state_handlers(),
)
def export_research_group_membership_graphs_manifest_flow(
    output_dir: str = "data/exports",
):
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.getcwd(), output_dir)

    generate_research_group_membership_graphs_manifest_task(output_dir)


if __name__ == "__main__":
    export_research_group_membership_graphs_manifest_flow()
