from contextlib import ExitStack
from unittest.mock import patch

from src.flows.exports.canonical_data import export_canonical_data_flow


def test_export_canonical_data_flow_calls_tracking_exports_individually(tmp_path):
    output_dir = str(tmp_path / "exports")

    with ExitStack() as stack:
        organizations_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_organizations_task")
        )
        campuses_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_campuses_task")
        )
        knowledge_areas_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_knowledge_areas_task")
        )
        researchers_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_researchers_task")
        )
        researchers_tracking_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_researchers_tracking_task")
        )
        groups_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_groups_task")
        )
        initiatives_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_initiatives_task")
        )
        initiatives_tracking_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_initiatives_tracking_task")
        )
        initiative_types_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_initiative_types_task")
        )
        articles_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_articles_task")
        )
        awards_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_awards_task")
        )
        languages_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_languages_task")
        )
        professional_activities_task = stack.enter_context(
            patch(
                "src.flows.exports.canonical_data.export_professional_activities_task"
            )
        )
        research_productions_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_research_productions_task")
        )
        advisorships_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_advisorships_task")
        )
        advisorships_tracking_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_advisorships_tracking_task")
        )
        ingestion_runs_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_ingestion_runs_task")
        )
        source_records_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_source_records_task")
        )
        entity_matches_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_entity_matches_task")
        )
        attribute_assertions_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_attribute_assertions_task")
        )
        entity_change_logs_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_entity_change_logs_task")
        )
        fellowships_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_fellowships_task")
        )
        advisorship_analytics_task = stack.enter_context(
            patch("src.flows.exports.canonical_data.export_advisorship_analytics_task")
        )
        people_relationship_graph_flow = stack.enter_context(
            patch(
                "src.flows.exports.canonical_data.export_people_relationship_graph_flow"
            )
        )
        for _graph_flow in (
            "export_people_collaboration_graph_flow",
            "export_researchers_collaboration_graph_flow",
            "export_students_collaboration_graph_flow",
            "export_outside_ifes_collaboration_graph_flow",
            "export_null_researchers_collaboration_graph_flow",
            "export_research_group_membership_graphs_manifest_flow",
        ):
            stack.enter_context(
                patch(f"src.flows.exports.canonical_data.{_graph_flow}")
            )
        stack.enter_context(patch("src.flows.exports.canonical_data.zip_exports_task"))
        makedirs = stack.enter_context(patch("os.makedirs"))
        export_canonical_data_flow.fn(output_dir=output_dir, campus="Serra")

    makedirs.assert_called_once_with(output_dir, exist_ok=True)
    organizations_task.assert_called_once_with(output_dir)
    campuses_task.assert_called_once_with(output_dir, "Serra")
    knowledge_areas_task.assert_called_once_with(output_dir)
    researchers_task.assert_called_once_with(output_dir, "Serra")
    researchers_tracking_task.assert_called_once_with(output_dir)
    groups_task.assert_called_once_with(output_dir, "Serra")
    initiatives_task.assert_called_once_with(output_dir)
    initiatives_tracking_task.assert_called_once_with(output_dir)
    initiative_types_task.assert_called_once_with(output_dir)
    articles_task.assert_called_once_with(output_dir)
    awards_task.assert_called_once_with(output_dir)
    languages_task.assert_called_once_with(output_dir)
    professional_activities_task.assert_called_once_with(output_dir)
    research_productions_task.assert_called_once_with(output_dir)
    advisorships_task.assert_called_once_with(output_dir)
    advisorships_tracking_task.assert_called_once_with(output_dir)
    ingestion_runs_task.assert_called_once_with(output_dir)
    source_records_task.assert_called_once_with(output_dir)
    entity_matches_task.assert_called_once_with(output_dir)
    attribute_assertions_task.assert_called_once_with(output_dir)
    entity_change_logs_task.assert_called_once_with(output_dir)
    fellowships_task.assert_called_once_with(output_dir)
    advisorship_analytics_task.assert_called_once_with(output_dir)
    people_relationship_graph_flow.assert_called_once_with(output_dir=output_dir)
