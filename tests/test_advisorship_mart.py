import json
from unittest.mock import MagicMock, mock_open, patch

from src.core.logic.canonical_exporter import CanonicalDataExporter
from src.core.ports.export_sink import IExportSink


def test_generate_advisorship_mart_calculates_correctly():
    # Arrange
    mock_sink = MagicMock(spec=IExportSink)
    exporter = CanonicalDataExporter(sink=mock_sink)

    sample_data = [
        {
            "id": 1,
            "name": "Project A",
            "advisorships": [
                {
                    "status": "Active",
                    "supervisor_name": "Dr. Silva",
                    "fellowship": {"name": "PIBITI", "value": 700.0}
                },
                {
                    "status": "Concluded",
                    "supervisor_name": "Dr. Santos",
                    "fellowship": {"name": "Voluntário", "value": 0.0}
                }
            ],
            "team": [{"name": "Member 1"}, {"name": "Member 2"}]
        },
        {
            "id": 2,
            "name": "Project B",
            "advisorships": [
                {
                    "status": "Active",
                    "supervisor_name": "Dr. Silva",
                    "fellowship": {"name": "PIBITI", "value": 700.0}
                }
            ],
            "team": [{"name": "Member 3"}]
        }
    ]

    json_input = json.dumps(sample_data)

    with patch("builtins.open", mock_open(read_data=json_input)):
        # Act
        exporter.generate_advisorship_mart("dummy_input.json", "dummy_output.json")

        # Assert
        assert mock_sink.export.call_count == 1
        args, _ = mock_sink.export.call_args
        final_mart = args[0][0]  # It exports a list containing the mart dict

        # Global Stats
        stats = final_mart["global_stats"]
        assert stats["total_projects"] == 2
        assert stats["total_advisorships"] == 3
        assert stats["total_active_advisorships"] == 2
        assert stats["total_monthly_investment"] == 1400.0
        assert stats["program_distribution"]["PIBITI"] == 2
        assert stats["program_distribution"]["Voluntário"] == 1
        assert stats["volunteer_count"] == 1
        assert stats["participation_ratio"] == 1.5  # 3/2
        assert stats["volunteer_percentage"] == 33.33  # (1/3)*100

        # Rankings
        rankings = final_mart["rankings"]
        assert rankings["top_supervisors"][0] == {"name": "Dr. Silva", "count": 2}
        assert rankings["top_projects_by_investment"][0]["name"] == "Project A"
        assert rankings["top_projects_by_investment"][0]["value"] == 700.0

        # Project Metrics
        projects = final_mart["projects"]
        assert len(projects) == 2
        p1 = next(p for p in projects if p["id"] == 1)
        assert p1["total_students"] == 2
        assert p1["active_students"] == 1
        assert p1["monthly_investment"] == 700.0
        assert p1["main_program"] == "PIBITI"
        assert p1["team_size"] == 2
