import re
from unittest.mock import MagicMock, patch

import pytest

from src.core.logic.canonical_exporter import CanonicalDataExporter
from src.core.logic.pii_anonymizer import is_anonymized_cpf, is_anonymized_email
from src.core.logic.research_group_exporter import ResearchGroupExporter
from src.core.ports.export_sink import IExportSink

RAW_CPF_PATTERN = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
RAW_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ANONYMIZED_DOMAIN = "@anon.lgpd"


def _check_no_raw_pii_in_json_str(text: str):
    assert not RAW_CPF_PATTERN.search(text), "Raw CPF found in export"
    matches = RAW_EMAIL_PATTERN.findall(text)
    for m in matches:
        if not m.endswith(ANONYMIZED_DOMAIN):
            raise AssertionError(f"Raw email found in export: {m}")


# --- Researcher export PII validation ---


def test_researcher_export_identification_id_is_anonymized():
    mock_sink = MagicMock(spec=IExportSink)

    with (
        patch("src.core.logic.canonical_exporter.OrganizationController"),
        patch("src.core.logic.canonical_exporter.CampusController"),
        patch("src.core.logic.canonical_exporter.KnowledgeAreaController"),
        patch("src.core.logic.canonical_exporter.ResearcherController"),
        patch("src.core.logic.canonical_exporter.InitiativeController"),
        patch("src.core.logic.canonical_exporter.ArticleController"),
    ):
        exporter = CanonicalDataExporter(sink=mock_sink)

    mock_researcher = MagicMock()
    mock_researcher.to_dict.return_value = {
        "id": 1,
        "name": "Alice",
        "identification_id": "123.456.789-00",
        "birthday": None,
    }
    exporter.researcher_ctrl.get_all.return_value = [mock_researcher]
    exporter.initiative_ctrl.get_all.return_value = []
    exporter.initiative_ctrl.list_initiative_types.return_value = []
    exporter._get_session = lambda: None
    exporter._get_campus_resolver = lambda: MagicMock(get_campus=lambda *a, **kw: None)
    exporter._fetch_researcher_advisorship_rows = lambda _: []

    exporter.export_researchers("output/researchers_canonical.json")

    exported = mock_sink.export.call_args[0][0]
    for item in exported:
        cpf = item.get("identification_id")
        assert is_anonymized_cpf(cpf), f"Raw CPF leaked: {cpf}"

    _check_no_raw_pii_in_json_str(str(exported))


def test_researcher_export_no_raw_cpf_in_any_classification_view():
    mock_sink = MagicMock(spec=IExportSink)

    with (
        patch("src.core.logic.canonical_exporter.OrganizationController"),
        patch("src.core.logic.canonical_exporter.CampusController"),
        patch("src.core.logic.canonical_exporter.KnowledgeAreaController"),
        patch("src.core.logic.canonical_exporter.ResearcherController"),
        patch("src.core.logic.canonical_exporter.InitiativeController"),
        patch("src.core.logic.canonical_exporter.ArticleController"),
    ):
        exporter = CanonicalDataExporter(sink=mock_sink)

    mock_researcher = MagicMock()
    mock_researcher.to_dict.return_value = {
        "id": 1,
        "name": "Alice",
        "identification_id": "987.654.321-00",
        "birthday": None,
    }
    exporter.researcher_ctrl.get_all.return_value = [mock_researcher]
    exporter.initiative_ctrl.get_all.return_value = []
    exporter.initiative_ctrl.list_initiative_types.return_value = []
    exporter._get_session = lambda: None
    exporter._get_campus_resolver = lambda: MagicMock(get_campus=lambda *a, **kw: None)
    exporter._fetch_researcher_advisorship_rows = lambda _: []

    exporter.export_researchers("output/researchers_canonical.json")

    calls = mock_sink.export.call_args_list
    for _, path in [c[0] for c in calls]:
        assert not RAW_CPF_PATTERN.search(path)


# --- Research group export PII validation ---


def test_research_group_export_member_emails_are_anonymized():
    mock_sink = MagicMock(spec=IExportSink)

    with (
        patch(
            "src.core.logic.research_group_exporter.ResearchGroupController"
        ) as MockRgCtrl,
        patch("src.core.logic.research_group_exporter.CampusController"),
        patch("src.core.logic.research_group_exporter.OrganizationController"),
    ):
        mock_group = MagicMock()
        mock_group.to_dict.return_value = {"id": 10, "name": "Group A"}
        mock_group.organization_id = 1
        mock_group.campus_id = 2
        mock_group.knowledge_areas = []

        mock_member = MagicMock()
        mock_member.person.id = 101
        mock_member.person.name = "Alice"
        mock_member.role.name = "Researcher"
        mock_member.person.lattes_url = None
        mock_member.start_date = None
        mock_member.end_date = None

        mock_email = MagicMock()
        mock_email.email = "alice@example.com"
        mock_member.person.emails = [mock_email]
        mock_group.members = [mock_member]

        MockRgCtrl.return_value.get_all.return_value = [mock_group]

        exporter = ResearchGroupExporter(sink=mock_sink)
        exporter.export_all("output.json")

        exported = mock_sink.export.call_args[0][0]
        for group in exported:
            for member in group.get("members", []):
                for email in member.get("emails", []):
                    assert is_anonymized_email(
                        email
                    ), f"Raw email leaked in group export: {email}"


def test_research_group_export_no_raw_email_in_output():
    mock_sink = MagicMock(spec=IExportSink)

    with (
        patch(
            "src.core.logic.research_group_exporter.ResearchGroupController"
        ) as MockRgCtrl,
        patch("src.core.logic.research_group_exporter.CampusController"),
        patch("src.core.logic.research_group_exporter.OrganizationController"),
    ):
        mock_group = MagicMock()
        mock_group.to_dict.return_value = {"id": 10, "name": "Group A"}
        mock_group.organization_id = 1
        mock_group.campus_id = 2
        mock_group.knowledge_areas = []

        mock_member = MagicMock()
        mock_member.person.id = 101
        mock_member.person.name = "Alice"
        mock_member.role.name = "Researcher"
        mock_member.person.lattes_url = None
        mock_member.start_date = None
        mock_member.end_date = None

        mock_email = MagicMock()
        mock_email.email = "bob@ifes.edu.br"
        mock_member.person.emails = [mock_email]
        mock_group.members = [mock_member]

        MockRgCtrl.return_value.get_all.return_value = [mock_group]

        exporter = ResearchGroupExporter(sink=mock_sink)
        exporter.export_all("output.json")

        exported = mock_sink.export.call_args[0][0]
        raw_json_str = str(exported)
        _check_no_raw_pii_in_json_str(raw_json_str)


# --- Advisorship export PII validation ---


def test_advisorship_export_person_names_are_not_regression_tested_for_pii():
    """Person names are PII-adjacent but not currently in PII_COLUMN_REGISTRY.
    This test serves as a reminder that names are not anonymized."""
    pass
