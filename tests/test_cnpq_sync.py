from types import SimpleNamespace
from unittest.mock import MagicMock

import src.core.logic.strategies.cnpq_sync as cnpq_sync_module
from src.core.logic.strategies.cnpq_sync import CnpqSyncLogic


def test_sync_members_uses_resume_fallback_for_new_researcher():
    logic = CnpqSyncLogic()

    session = MagicMock()
    researcher_check = MagicMock()
    researcher_check.scalar.return_value = True
    session.execute.return_value = researcher_check

    logic.rg_ctrl = MagicMock()
    logic.rg_ctrl._service._repository._session = session
    logic.rg_ctrl._service.get_members.return_value = []
    logic.res_ctrl = MagicMock()
    logic.res_ctrl.get_all.return_value = []
    logic.role_ctrl = MagicMock()
    logic.role_ctrl.get_all.return_value = []
    logic.role_ctrl.create_role.return_value = SimpleNamespace(id=7, name="Pesquisador")
    logic.ka_ctrl = MagicMock()

    logic.res_ctrl.create_researcher.side_effect = TypeError(
        "create_with_details() got an unexpected keyword argument 'resume'"
    )
    created = MagicMock()
    created.id = 123
    logic.res_ctrl._service.create_with_details.return_value = created
    researcher_check_exists = MagicMock()
    researcher_check_exists.scalar.return_value = True
    logic.res_ctrl._service._repository._session.execute.return_value = (
        researcher_check_exists
    )
    logic.res_ctrl.get_by_id.return_value = created

    logic.sync_members(
        group_id=10,
        members_data=[
            {
                "name": "Alice",
                "role": "Pesquisador",
                "data_inicio": None,
                "data_fim": None,
            }
        ],
    )

    logic.res_ctrl.create_researcher.assert_called_once_with(
        name="Alice",
        identification_id="Alice",
        emails=None,
    )
    logic.res_ctrl._service.create_with_details.assert_called_once_with(
        name="Alice",
        identification_id="Alice",
        emails=None,
    )
    assert session.commit.called
    logic.rg_ctrl._service.add_member.assert_called_once_with(
        team_id=10,
        person_id=123,
        role_id=7,
        start_date=None,
        end_date=None,
    )


def test_sync_group_coerces_dict_description_before_update():
    logic = CnpqSyncLogic()

    session = MagicMock()
    current_row = MagicMock()
    current_row.fetchone.return_value = ("Grupo Atual", None)
    session.execute.side_effect = [current_row, MagicMock()]

    logic.rg_ctrl = MagicMock()
    logic.rg_ctrl._service._repository._session = session

    logic.sync_group(
        group_id=87,
        cnpq_data={
            "nome_grupo": "Grupo Atual",
            "repercussoes": {"descricao": "Descricao normalizada do grupo"},
        },
    )

    update_params = session.execute.call_args_list[1].args[1]
    assert update_params["description"] == "Descricao normalizada do grupo"
    assert update_params["gid"] == 87
    session.commit.assert_called()


def test_sync_knowledge_areas_tracks_associations_after_commit(monkeypatch):
    logic = CnpqSyncLogic()

    session = MagicMock()
    existence_check = MagicMock()
    existence_check.fetchone.return_value = None
    session.execute.side_effect = [existence_check, MagicMock()]

    events = []
    session.commit.side_effect = lambda: events.append("commit")

    logic.rg_ctrl = MagicMock()
    logic.rg_ctrl._service._repository._session = session
    logic.ka_ctrl = MagicMock()
    logic.ka_ctrl.get_all.return_value = [SimpleNamespace(id=55, name="Linha A")]

    tracker = MagicMock()
    tracker.record_source_record.return_value = SimpleNamespace(id=91)
    tracker.record_entity_match.side_effect = lambda **kwargs: events.append("match")
    tracker.record_attribute_assertions.side_effect = lambda **kwargs: events.append(
        "assert"
    )
    tracker.record_change.side_effect = lambda **kwargs: events.append("change")
    monkeypatch.setattr(cnpq_sync_module, "tracking_recorder", tracker)

    logic.sync_knowledge_areas(
        group_id=10,
        lines_data=[{"nome_da_linha_de_pesquisa": "Linha A"}],
        source_file="grupo.json",
    )

    assert events == ["commit", "match", "assert", "change"]
