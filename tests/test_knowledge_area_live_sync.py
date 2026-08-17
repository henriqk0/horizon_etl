import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from src.core.logic.initiative_linker import InitiativeLinker
from src.core.logic.research_group_loader import ResearchGroupLoader


class _FakeKnowledgeArea:
    def __init__(self, id, name):
        self.id = id
        self.name = name


def test_existing_group_resyncs_knowledge_areas_on_reingestion():
    """User Story 3 (research_group_loader.py): an existing group's knowledge
    areas are updated on re-ingestion, not only set at creation time."""
    with (
        patch("src.core.logic.research_group_loader.UniversityController"),
        patch("src.core.logic.research_group_loader.CampusController"),
        patch(
            "src.core.logic.research_group_loader.ResearchGroupController"
        ) as MockRgCtrl,
        patch(
            "src.core.logic.research_group_loader.KnowledgeAreaController"
        ) as MockAreaCtrl,
        patch("src.core.logic.research_group_loader.ResearcherController"),
        patch("src.core.logic.research_group_loader.RoleController"),
    ):
        mock_rg_instance = MockRgCtrl.return_value
        mock_area_instance = MockAreaCtrl.return_value

        existing_group = MagicMock()
        existing_group.id = 1
        existing_group.name = "Group A"
        existing_group.cnpq_url = None
        existing_group.knowledge_areas = []  # no areas yet, despite having existed

        mock_rg_instance.get_all.return_value = [existing_group]
        new_area = _FakeKnowledgeArea(id=101, name="Metodologias Ágeis")
        mock_area_instance.get_by_id.return_value = new_area

        mapping_strategy = MagicMock()
        mapping_strategy.map_row.return_value = {
            "name": "Group A",
            "short_name": None,
            "campus_name": "Serra",
            "area_name": "Metodologias Ágeis",
            "site_url": None,
            "leaders_raw": None,
        }
        mapping_strategy.parse_leaders.return_value = []

        org_strategy = MagicMock()
        org_strategy.ensure.return_value = 1
        campus_strategy = MagicMock()
        campus_strategy.ensure.return_value = 1
        area_strategy = MagicMock()
        area_strategy.ensure.return_value = 101
        researcher_strategy = MagicMock()
        role_strategy = MagicMock()

        loader = ResearchGroupLoader(
            mapping_strategy=mapping_strategy,
            org_strategy=org_strategy,
            campus_strategy=campus_strategy,
            area_strategy=area_strategy,
            researcher_strategy=researcher_strategy,
            role_strategy=role_strategy,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "groups.xlsx"
            pd.DataFrame([{"name": "Group A"}]).to_excel(xlsx_path, index=False)
            loader.process_file(str(xlsx_path))

        assert new_area in existing_group.knowledge_areas
        mock_rg_instance.update.assert_called_with(existing_group)


def test_initiative_without_keywords_derives_areas_from_group():
    """User Story 3 (initiative_linker.py): an initiative lacking metadata.keywords
    still receives knowledge areas derived from its linked research group."""
    rg_controller = MagicMock()
    target_group = MagicMock()
    target_group.id = 1
    target_group.name = "Group A"
    rg_controller.get_all.return_value = [target_group]

    session = MagicMock()
    rg_controller._service._repository._session = session
    session.execute.return_value.fetchall.return_value = [(101,)]
    session.execute.return_value.scalar.return_value = None

    person_matcher = MagicMock()
    person_matcher.match_or_create.return_value = None

    linker = InitiativeLinker(
        initiative_controller=MagicMock(),
        rg_controller=rg_controller,
        team_controller=MagicMock(),
        person_matcher=person_matcher,
        team_synchronizer=MagicMock(),
        entity_manager=MagicMock(),
    )

    initiative = MagicMock()
    initiative.id = 10
    project_data = {"metadata": {}}

    linker.associate_keyword_knowledge_areas(initiative, project_data, "Group A")

    # The derived area (101) must have been used as the area_id bound parameter
    insert_calls = [
        call
        for call in session.execute.call_args_list
        if "INSERT INTO initiative_knowledge_areas" in str(call.args[0])
    ]
    assert insert_calls, "Expected an INSERT into initiative_knowledge_areas"
    assert insert_calls[0].args[1] == {"iid": 10, "aid": 101}


def test_initiative_with_keywords_still_uses_keyword_path():
    """Regression guard: when metadata.keywords IS present, the existing
    keyword-based linkage path is used, not the group-derivation fallback."""
    rg_controller = MagicMock()
    session = MagicMock()
    rg_controller._service._repository._session = session
    session.execute.return_value.scalar.return_value = None

    entity_manager = MagicMock()
    entity_manager.ensure_knowledge_area.return_value = 200

    person_matcher = MagicMock()
    person_matcher.match_or_create.return_value = None

    linker = InitiativeLinker(
        initiative_controller=MagicMock(),
        rg_controller=rg_controller,
        team_controller=MagicMock(),
        person_matcher=person_matcher,
        team_synchronizer=MagicMock(),
        entity_manager=entity_manager,
    )
    linker._get_all_groups = MagicMock(return_value=[])

    initiative = MagicMock()
    initiative.id = 10
    project_data = {"metadata": {"keywords": "IA, Robótica"}}

    linker.associate_keyword_knowledge_areas(initiative, project_data, None)

    entity_manager.ensure_knowledge_area.assert_any_call("IA")
    entity_manager.ensure_knowledge_area.assert_any_call("Robótica")
