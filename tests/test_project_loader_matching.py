from unittest.mock import MagicMock

from research_domain.domain.entities import Advisorship

from src.core.logic.initiative_identity import normalize_text
from src.core.logic.project_loader import ProjectLoader


def test_resolve_existing_initiative_prefers_same_model_when_identity_hits_wrong_type():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    loader.controller = MagicMock()

    research_project = MagicMock()
    research_project.id = 1338

    advisorship = MagicMock(spec=Advisorship)
    advisorship.id = 113

    loader.adv_controller.get_by_id.side_effect = [None, advisorship]

    existing = loader._resolve_existing_initiative(
        existing_by_name={
            normalize_text(
                "Instrumentação de um robô móvel para serviços de vigilância."
            ): advisorship
        },
        existing_by_identity={
            "instrumentacao de um robo movel para servicos de vigilancia": research_project
        },
        model_class=Advisorship,
        identity_key="instrumentacao de um robo movel para servicos de vigilancia",
        title="Instrumentação de um robô móvel para serviços de vigilância.",
    )

    assert existing is advisorship


def test_resolve_existing_initiative_matches_case_accent_variants():
    loader = ProjectLoader.__new__(ProjectLoader)

    research_project = MagicMock()
    research_project.id = 4

    loader.adv_controller = MagicMock()
    loader.adv_controller.get_by_id.return_value = None

    existing = loader._resolve_existing_initiative(
        existing_by_name={
            normalize_text(
                "Otimização da eficiência energética do uso de gás na siderurgia"
            ): research_project
        },
        existing_by_identity={},
        model_class=MagicMock,
        identity_key=None,
        title="otimizacao da eficiencia energetica do uso de gas na siderurgia",
    )

    assert existing is research_project


def test_register_existing_initiative_keeps_parent_mapping_when_child_shares_title():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    loader.adv_controller.get_by_id.return_value = None

    parent_project = MagicMock()
    parent_project.id = 258

    child_advisorship = MagicMock(spec=Advisorship)
    child_advisorship.id = 999

    title = "Desenvolvimento de uma plataforma de aquisição de sinais cerebrais para projetos orientados a robótica"

    existing_by_name = {normalize_text(title): parent_project}

    loader._register_existing_initiative(
        existing_by_name=existing_by_name,
        title=title,
        initiative=child_advisorship,
        model_class=Advisorship,
    )

    assert existing_by_name[normalize_text(title)] is parent_project


def test_register_existing_initiative_stores_normalized_key():
    loader = ProjectLoader.__new__(ProjectLoader)
    loader.adv_controller = MagicMock()
    loader.adv_controller.get_by_id.return_value = None

    initiative = MagicMock(spec=Advisorship)
    initiative.id = 10

    existing_by_name = {}
    loader._register_existing_initiative(
        existing_by_name=existing_by_name,
        title="CAFÉ DA MANHÃ - Pesquisa",
        initiative=initiative,
        model_class=Advisorship,
    )

    assert normalize_text("CAFÉ DA MANHÃ - Pesquisa") in existing_by_name
    assert "cafe da manha pesquisa" in existing_by_name
    assert existing_by_name["cafe da manha pesquisa"] is initiative
