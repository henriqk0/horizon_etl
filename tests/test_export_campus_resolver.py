import unittest
from unittest.mock import MagicMock

from src.core.logic.export_campus_resolver import ExportCampusResolver


class TestExportCampusResolverStudentCascade(unittest.TestCase):
    """Unit tests for the 3-tier student campus allocation cascade in ExportCampusResolver."""

    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_campus_ctrl = MagicMock()

        # Mock campus_ctrl.get_all() returning 3 campuses
        self.mock_campus_ctrl.get_all.return_value = [
            {"id": 1, "name": "Campus Serra"},
            {"id": 2, "name": "Campus Vitória"},
            {"id": 3, "name": "Campus Vila Velha"},
        ]

        self.resolver = ExportCampusResolver(self.mock_session, self.mock_campus_ctrl)

    def test_level1_project_campus_resolution(self):
        """User Story 1: Students in projects with valid campus resolve via Level 1 (project)."""
        # Set level 1 state directly
        self.resolver._campus_by_id = {
            1: {"id": 1, "name": "Campus Serra"},
            2: {"id": 2, "name": "Campus Vitória"},
        }
        self.resolver._student_level1_project_campuses[101][
            1
        ] = 3  # Student 101 -> Campus Serra
        self.resolver._loaded = True

        campuses = self.resolver.get_student_campuses(101)
        self.assertEqual(len(campuses), 1)
        self.assertEqual(campuses[0]["name"], "Campus Serra")

        audit = self.resolver.get_student_resolution_audit(101)
        self.assertEqual(audit["resolved_via"], "project")
        self.assertEqual(audit["confidence"], "high")

        primary = self.resolver.get_campus("student", 101)
        self.assertIsNotNone(primary)
        self.assertEqual(primary["name"], "Campus Serra")

    def test_level2_group_fallback_resolution(self):
        """User Story 2: Students with no project campus fallback to Level 2 (research group)."""
        self.resolver._campus_by_id = {
            1: {"id": 1, "name": "Campus Serra"},
            2: {"id": 2, "name": "Campus Vitória"},
        }
        # Student 202 has NO level 1 project campus, but has Level 2 group campus
        self.resolver._student_level2_group_campuses[202][
            2
        ] = 2  # Student 202 -> Campus Vitória
        self.resolver._loaded = True

        campuses = self.resolver.get_student_campuses(202)
        self.assertEqual(len(campuses), 1)
        self.assertEqual(campuses[0]["name"], "Campus Vitória")

        audit = self.resolver.get_student_resolution_audit(202)
        self.assertEqual(audit["resolved_via"], "research_group")
        self.assertEqual(audit["confidence"], "medium")

    def test_level3_main_advisor_fallback_and_multi_campus(self):
        """User Story 3: Students with no project/group campus fallback to Level 3 (main advisor) with multi-campus support."""
        self.resolver._campus_by_id = {
            1: {"id": 1, "name": "Campus Serra"},
            2: {"id": 2, "name": "Campus Vitória"},
            3: {"id": 3, "name": "Campus Vila Velha"},
        }
        # Student 303 has NO Level 1 or Level 2, but has Level 3 main advisor campuses (tie between 1 and 2)
        self.resolver._student_level3_advisor_campuses[303][1] = 1
        self.resolver._student_level3_advisor_campuses[303][2] = 1
        self.resolver._loaded = True

        campuses = self.resolver.get_student_campuses(303)
        self.assertEqual(len(campuses), 2)
        campus_names = [c["name"] for c in campuses]
        self.assertIn("Campus Serra", campus_names)
        self.assertIn("Campus Vitória", campus_names)

        audit = self.resolver.get_student_resolution_audit(303)
        self.assertEqual(audit["resolved_via"], "main_advisor")
        self.assertEqual(audit["confidence"], "low")

    def test_unresolved_student(self):
        """Unresolved student with no project, group, or advisor campus returns empty list and unresolved audit."""
        self.resolver._campus_by_id = {1: {"id": 1, "name": "Campus Serra"}}
        self.resolver._loaded = True

        campuses = self.resolver.get_student_campuses(999)
        self.assertEqual(campuses, [])

        audit = self.resolver.get_student_resolution_audit(999)
        self.assertEqual(audit["resolved_via"], "unresolved")
        self.assertEqual(audit["confidence"], "low")

        primary = self.resolver.get_campus("student", 999)
        self.assertIsNone(primary)


if __name__ == "__main__":
    unittest.main()
