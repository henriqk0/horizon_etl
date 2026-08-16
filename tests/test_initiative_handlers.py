from datetime import datetime
from unittest.mock import MagicMock, call, patch

from research_domain.domain.entities import Advisorship

from src.core.logic.initiative_handlers import AdvisorshipHandler


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_creates_members_with_base_persons(
    MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    student_role = MagicMock()
    student_role.id = 1
    student_role.name = "Student"

    supervisor_role = MagicMock()
    supervisor_role.id = 2
    supervisor_role.name = "Supervisor"

    entity_manager.role_controller.get_all.return_value = [
        student_role,
        supervisor_role,
    ]
    MockFellowshipController.return_value.get_all.return_value = []

    session = MagicMock()
    session.execute.return_value.scalar.return_value = None
    session.execute.return_value.all.return_value = []
    person_matcher.person_controller._service._repository._session = session
    initiative_controller._service._repository._session = session

    student_match = MagicMock()
    student_match.id = 11
    supervisor_match = MagicMock()
    supervisor_match.id = 12
    student_person = MagicMock()
    student_person.id = 11
    supervisor_person = MagicMock()
    supervisor_person.id = 12

    person_matcher.match_or_create.side_effect = [student_match, supervisor_match]
    session.get.side_effect = [student_person, supervisor_person]
    person_matcher.person_controller.get_by_id.side_effect = [
        student_person,
        supervisor_person,
    ]

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    project_data = {
        "title": "Test Advisorship",
        "student_names": ["Student A"],
        "student_emails": ["student@example.org"],
        "coordinator_name": "Supervisor B",
        "coordinator_email": "supervisor@example.org",
        "status": "active",
    }

    created = handler.create_or_update(
        project_data=project_data,
        existing_initiative=None,
        initiative_type_name="Advisorship",
        initiative_type_id=7,
        organization_id=9,
        parent_id=10,
    )

    assert isinstance(created, Advisorship)
    MockAdvisorshipController.return_value.create_advisorship.assert_not_called()
    MockAdvisorshipController.return_value.create.assert_called_once_with(created)
    assert [member.person for member in created.members] == [
        student_person,
        supervisor_person,
    ]
    assert [member.role_name for member in created.members] == [
        "Student",
        "Supervisor",
    ]
    assert created.initiative_type_id == 7
    assert created.organization_id == 9
    assert created.parent_id == 10


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_disambiguates_title_when_name_is_already_taken(
    _MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    session = MagicMock()
    session.execute.return_value.scalar.return_value = 258
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    title = handler._resolve_persisted_title(
        "Desenvolvimento de uma Bancada Didática de Baixo Custo",
        {
            "student_names": ["Ana Estudante"],
            "start_date": datetime(2019, 8, 1),
            "metadata": {"sigpesq_id": 123},
        },
    )

    assert (
        title
        == "Desenvolvimento de uma Bancada Didática de Baixo Custo | Orientacao Ana Estudante | 2019 | sigpesq 123"
    )


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_supports_legacy_student_and_supervisor_fields(
    _MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    session = MagicMock()
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    class LegacyAdvisorship:
        student = None
        student_id = None
        supervisor = None
        supervisor_id = None

    initiative = LegacyAdvisorship()
    student = MagicMock()
    student.id = 11
    supervisor = MagicMock()
    supervisor.id = 12

    with patch.object(handler, "_coerce_to_person", side_effect=[student, supervisor]):
        handler._sync_advisorship_member(
            initiative,
            person=student,
            role_name="Student",
            start_date=None,
        )
        handler._sync_advisorship_member(
            initiative,
            person=supervisor,
            role_name="Supervisor",
            start_date=None,
        )

    assert initiative.student is student
    assert initiative.student_id == 11
    assert initiative.supervisor is supervisor
    assert initiative.supervisor_id == 12


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_reuses_fellowships_by_program_and_sponsor_across_workplans(
    _MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    entity_manager.ensure_organization.side_effect = [101, 102]
    session = MagicMock()
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    first = handler._ensure_fellowship(
        {
            "fellowship_data": {
                "name": "PIVIC",
                "sponsor_name": "Voluntario",
                "value": 700.0,
                "sigpesq_workplan_code": "17515",
                "sigpesq_project_code": "8748",
            }
        }
    )
    second = handler._ensure_fellowship(
        {
            "fellowship_data": {
                "name": "PIVIC",
                "sponsor_name": "Voluntario",
                "value": 700.0,
                "sigpesq_workplan_code": "17548",
                "sigpesq_project_code": "8752",
            }
        }
    )
    again_first = handler._ensure_fellowship(
        {
            "fellowship_data": {
                "name": "PIVIC",
                "sponsor_name": "Voluntario",
                "value": 700.0,
                "sigpesq_workplan_code": "17515",
                "sigpesq_project_code": "8748",
            }
        }
    )
    cnpq = handler._ensure_fellowship(
        {
            "fellowship_data": {
                "name": "PIVIC",
                "sponsor_name": "CNPq",
                "value": 700.0,
                "sigpesq_workplan_code": "17549",
                "sigpesq_project_code": "8753",
            }
        }
    )

    assert second is first
    assert again_first is first
    assert cnpq is not first
    assert first.sponsor_id == 101
    assert cnpq.sponsor_id == 102
    entity_manager.ensure_organization.assert_has_calls(
        [call(name="Voluntario"), call(name="CNPq")]
    )
    assert MockFellowshipController.return_value.create.call_count == 2


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_sets_cancelled_on_created_advisorship(
    MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    session = MagicMock()
    session.execute.return_value.scalar.return_value = None
    session.execute.return_value.all.return_value = []
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    created = handler.create_or_update(
        project_data={
            "title": "Plano cancelado",
            "status": "Cancelled",
            "cancelled": True,
            "cancellation_date": None,
        },
        existing_initiative=None,
        initiative_type_name="Advisorship",
        initiative_type_id=7,
        organization_id=9,
        parent_id=10,
    )

    assert created.cancelled is True
    assert created.cancellation_date is None
    MockAdvisorshipController.return_value.create.assert_called_once_with(created)


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_skips_resync_when_membership_matches(
    _MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    session = MagicMock()
    session.execute.return_value.scalar.return_value = None
    session.execute.return_value.all.return_value = []
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    existing_member = MagicMock()
    existing_member.role_name = "Student"
    existing_member.person_id = 11
    existing_member.start_date = None

    initiative = MagicMock()
    original_members = [existing_member]
    initiative.members = original_members
    initiative.add_member = MagicMock()

    person = MagicMock()
    person.id = 11

    with patch.object(handler, "_coerce_to_person", return_value=person):
        handler._sync_advisorship_member(
            initiative,
            person=person,
            role_name="Student",
            start_date=None,
        )

    initiative.add_member.assert_not_called()
    assert initiative.members is original_members


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_resyncs_when_membership_changed(
    _MockAdvisorshipController,
    MockFellowshipController,
):
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    entity_manager.role_controller.get_all.return_value = []
    session = MagicMock()
    session.execute.return_value.scalar.return_value = None
    session.execute.return_value.all.return_value = []
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    stale_member = MagicMock()
    stale_member.role_name = "Student"
    stale_member.person_id = 11
    stale_member.start_date = None

    initiative = MagicMock()
    initiative.members = [stale_member]
    initiative.add_member = MagicMock()

    new_person = MagicMock()
    new_person.id = 12

    with patch.object(handler, "_coerce_to_person", return_value=new_person):
        handler._sync_advisorship_member(
            initiative,
            person=new_person,
            role_name="Student",
            start_date=None,
        )

    initiative.add_member.assert_called_once()
    assert initiative.add_member.call_args.kwargs["person"] is new_person
    assert initiative.add_member.call_args.kwargs["start_date"] is None
    assert initiative.members == []


@patch("src.core.logic.initiative_handlers.FellowshipController")
@patch("src.core.logic.initiative_handlers.AdvisorshipController")
def test_advisorship_handler_merges_historical_raw_title_record(
    MockAdvisorshipController,
    MockFellowshipController,
):
    """An advisorship stored under its raw title must be merged (not duplicated)
    once a same-named project forces a disambiguated title."""
    initiative_controller = MagicMock()
    person_matcher = MagicMock()
    entity_manager = MagicMock()

    MockFellowshipController.return_value.get_all.return_value = []
    entity_manager.role_controller.get_all.return_value = []

    session = MagicMock()
    session.execute.return_value.scalar.return_value = 1  # raw title in use
    initiative_controller._service._repository._session = session
    person_matcher.person_controller._service._repository._session = session
    MockAdvisorshipController.return_value.get_by_id.return_value = MagicMock(
        spec=Advisorship
    )

    handler = AdvisorshipHandler(
        initiative_controller=initiative_controller,
        person_matcher=person_matcher,
        entity_manager=entity_manager,
    )

    raw_title = "Consumo inteligente de energia"
    disambiguated = "Consumo inteligente de energia | Orientacao Aluno A | 2022"

    historical = MagicMock(spec=Advisorship)
    historical.id = 777

    # persisted (disambiguated) not found, but the raw title exists historically
    with (
        patch.object(
            handler,
            "_find_existing_advisorship_by_title",
            side_effect=lambda name, **kwargs: (
                historical if name == raw_title else None
            ),
        ),
        patch.object(
            handler,
            "_resolve_advisorship_people",
            return_value=(None, None),
        ),
        patch.object(handler, "_handle_advisorship_details"),
        patch.object(handler, "_sync_advisorship_cancellation"),
    ):
        result = handler.create_or_update(
            project_data={
                "title": raw_title,
                "student_names": ["Aluno A"],
                "start_date": datetime(2022, 1, 1),
            },
            existing_initiative=None,
            initiative_type_name="Advisorship",
            initiative_type_id=2,
            organization_id=1,
        )

    assert result is historical
    assert result.id == 777
    MockAdvisorshipController.return_value.update.assert_called()
    MockAdvisorshipController.return_value.create.assert_not_called()
