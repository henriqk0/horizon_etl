from unittest.mock import MagicMock, patch


from src.core.logic.research_group_exporter import ResearchGroupExporter
from src.core.ports.export_sink import IExportSink


def test_exporter_fetches_and_exports_enriched_data():
    # Arrange
    mock_sink = MagicMock(spec=IExportSink)

    with (
        patch(
            "src.core.logic.research_group_exporter.ResearchGroupController"
        ) as MockRgCtrl,
        patch(
            "src.core.logic.research_group_exporter.CampusController"
        ) as MockCampCtrl,
        patch(
            "src.core.logic.research_group_exporter.OrganizationController"
        ) as MockOrgCtrl,
    ):

        # Mock Instances
        mock_rg_instance = MockRgCtrl.return_value
        mock_camp_instance = MockCampCtrl.return_value
        mock_org_instance = MockOrgCtrl.return_value

        # Mock Data - Organizations
        mock_org = MagicMock()
        mock_org.id = 1
        mock_org.name = "Test Org"
        mock_org_instance.get_all.return_value = [mock_org]

        # Mock Data - Campuses
        mock_campus = MagicMock()
        mock_campus.id = 2
        mock_campus.name = "Test Campus"
        mock_camp_instance.get_all.return_value = [mock_campus]

        # Mock Data - Research Group
        mock_group = MagicMock()
        mock_group.to_dict.return_value = {
            "id": 10,
            "organization_id": 1,
            "campus_id": 2,
            "name": "Group A",
        }
        mock_group.organization_id = 1
        mock_group.campus_id = 2

        # Mock Knowledge Areas
        mock_ka = MagicMock()
        mock_ka.id = 55
        mock_ka.name = "Computer Science"
        mock_group.knowledge_areas = [mock_ka]

        # Mock Members
        mock_member = MagicMock()
        mock_member.person.id = 101
        mock_member.person.name = "Alice"
        mock_member.role.name = "Researcher"
        mock_member.person.lattes_url = "http://lattes/alice"

        mock_start_date = MagicMock()
        mock_start_date.strftime.return_value = "2026-01-01"
        mock_end_date = MagicMock()
        mock_end_date.strftime.return_value = "2026-12-31"

        mock_member.start_date = mock_start_date
        mock_member.end_date = mock_end_date

        # Mock Emails for Alice
        mock_email = MagicMock()
        mock_email.email = "alice@example.com"
        mock_member.person.emails = [mock_email]

        mock_leader = MagicMock()
        mock_leader.person.id = 102
        mock_leader.person.name = "Bob"
        mock_leader.role.name = "Líder"
        mock_leader.person.lattes_url = "http://lattes/bob"
        mock_leader.start_date = mock_start_date
        mock_leader.end_date = mock_end_date

        # Mock Emails for Bob
        mock_leader_email = MagicMock()
        mock_leader_email.email = "bob@example.com"
        mock_leader.person.emails = [mock_leader_email]

        mock_group.members = [mock_member, mock_leader]

        mock_rg_instance.get_all.return_value = [mock_group]

        exporter = ResearchGroupExporter(sink=mock_sink)

        # Act
        exporter.export_all("output.json")

        # Assert
        mock_rg_instance.get_all.assert_called_once()
        mock_org_instance.get_all.assert_called_once()
        mock_camp_instance.get_all.assert_called_once()

        # Verify Export Content
        expected_data = [
            {
                "id": 10,
                "organization_id": 1,
                "campus_id": 2,
                "name": "Group A",
                "organization": {"id": 1, "name": "Test Org"},
                "campus": {"id": 2, "name": "Test Campus"},
                "knowledge_areas": [{"id": 55, "name": "Computer Science"}],
                "members": [
                    {
                        "id": 101,
                        "name": "Alice",
                        "role": "Researcher",
                        "lattes_url": "http://lattes/alice",
                        "emails": ["alice@example.com"],
                        "start_date": "2026-01-01",
                        "end_date": "2026-12-31",
                    },
                    {
                        "id": 102,
                        "name": "Bob",
                        "role": "Líder",
                        "lattes_url": "http://lattes/bob",
                        "emails": ["bob@example.com"],
                        "start_date": "2026-01-01",
                        "end_date": "2026-12-31",
                    },
                ],
                "leaders": [
                    {
                        "id": 102,
                        "name": "Bob",
                        "role": "Líder",
                        "lattes_url": "http://lattes/bob",
                        "emails": ["bob@example.com"],
                        "start_date": "2026-01-01",
                        "end_date": "2026-12-31",
                    }
                ],
            }
        ]
        mock_sink.export.assert_called_once_with(expected_data, "output.json")


def test_exporter_handles_empty_list():
    # Arrange
    mock_sink = MagicMock(spec=IExportSink)

    with patch(
        "src.core.logic.research_group_exporter.ResearchGroupController"
    ) as MockCtrl:
        mock_ctrl_instance = MockCtrl.return_value
        mock_ctrl_instance.get_all.return_value = []

        exporter = ResearchGroupExporter(sink=mock_sink)

        # Act
        exporter.export_all("output.json")

        # Assert
        mock_ctrl_instance.get_all.assert_called_once()
        mock_sink.export.assert_not_called()
