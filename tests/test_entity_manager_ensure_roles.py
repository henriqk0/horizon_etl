from unittest.mock import MagicMock, patch

import pytest

from src.core.logic.entity_manager import EntityManager


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@patch("src.core.logic.entity_manager.CampusController")
@patch("src.core.logic.entity_manager.KnowledgeAreaController")
@patch("src.core.logic.entity_manager.RoleController")
@patch("src.core.logic.entity_manager.UniversityController")
@patch("src.core.logic.entity_manager.EducationTypeController")
@patch("src.core.logic.entity_manager.AcademicEducationController")
@patch("src.core.logic.entity_manager.ArticleController")
@patch("src.core.logic.entity_manager.OrganizationController")
def test_ensure_roles_returns_full_cache_when_controller_succeeds(
    MockOrgCtrl,
    MockArticleCtrl,
    MockAcademicEduCtrl,
    MockEduTypeCtrl,
    MockUniCtrl,
    MockRoleCtrl,
    MockKaCtrl,
    MockCampusCtrl,
):
    MockRoleCtrl.return_value.get_all.return_value = [
        Obj(name="Coordinator"),
        Obj(name="Researcher"),
    ]
    MockRoleCtrl.return_value.create_role.side_effect = lambda name, description: Obj(
        name=name
    )

    manager = EntityManager(MagicMock(), MagicMock())
    roles = manager.ensure_roles()

    assert set(roles.keys()) == set(EntityManager.ROLES)


@patch("src.core.logic.entity_manager.PostgresClient")
@patch("src.core.logic.entity_manager.CampusController")
@patch("src.core.logic.entity_manager.KnowledgeAreaController")
@patch("src.core.logic.entity_manager.RoleController")
@patch("src.core.logic.entity_manager.UniversityController")
@patch("src.core.logic.entity_manager.EducationTypeController")
@patch("src.core.logic.entity_manager.AcademicEducationController")
@patch("src.core.logic.entity_manager.ArticleController")
@patch("src.core.logic.entity_manager.OrganizationController")
def test_ensure_roles_raises_when_controller_and_fallback_both_fail(
    MockOrgCtrl,
    MockArticleCtrl,
    MockAcademicEduCtrl,
    MockEduTypeCtrl,
    MockUniCtrl,
    MockRoleCtrl,
    MockKaCtrl,
    MockCampusCtrl,
    MockPostgresClient,
):
    """Regression guard for the incident documented in relatorio.md §4.6:
    an empty roles table silently misclassified 9,556 people. ensure_roles()
    must now fail loudly instead of returning an incomplete cache."""
    MockRoleCtrl.return_value.get_all.side_effect = RuntimeError("db down")
    MockPostgresClient.return_value.get_session.side_effect = RuntimeError(
        "fallback db down too"
    )

    manager = EntityManager(MagicMock(), MagicMock())

    with pytest.raises(RuntimeError, match="Failed to ensure required roles exist"):
        manager.ensure_roles()


@patch("src.core.logic.entity_manager.PostgresClient")
@patch("src.core.logic.entity_manager.CampusController")
@patch("src.core.logic.entity_manager.KnowledgeAreaController")
@patch("src.core.logic.entity_manager.RoleController")
@patch("src.core.logic.entity_manager.UniversityController")
@patch("src.core.logic.entity_manager.EducationTypeController")
@patch("src.core.logic.entity_manager.AcademicEducationController")
@patch("src.core.logic.entity_manager.ArticleController")
@patch("src.core.logic.entity_manager.OrganizationController")
def test_ensure_roles_succeeds_via_fallback_when_controller_fails(
    MockOrgCtrl,
    MockArticleCtrl,
    MockAcademicEduCtrl,
    MockEduTypeCtrl,
    MockUniCtrl,
    MockRoleCtrl,
    MockKaCtrl,
    MockCampusCtrl,
    MockPostgresClient,
):
    MockRoleCtrl.return_value.get_all.side_effect = RuntimeError("db down")

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    MockPostgresClient.return_value.get_session.return_value = session

    manager = EntityManager(MagicMock(), MagicMock())
    roles = manager.ensure_roles()

    assert set(roles.keys()) == set(EntityManager.ROLES)
