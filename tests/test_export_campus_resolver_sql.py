"""Campus resolution exercised against real SQL, not mocks.

The sibling test module drives the student cascade through mocked state, which
cannot catch a defect in the SQL itself — and that is exactly where campus
resolution broke. Two independent faults blanked the campus of entire entity
types while the export still reported success:

* the article query selected ``a.id`` from a ``FROM`` clause that never
  aliased anything ``a``, so it raised and was swallowed into an empty result;
* the initiative and advisorship queries reached the campus through
  ``research_groups.id = initiative_teams.team_id``, which stopped matching
  once spec 014 gave initiative teams ids disjoint from research groups.

Both surfaced only as ``campus: null`` in the export, which emptied projects
and publications out of any campus-filtered dashboard view. These tests run
the resolver over a real in-memory schema shaped like the post-spec-014
database, so a regression fails here instead of silently shipping.
"""

import unittest
from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.core.logic.export_campus_resolver import ExportCampusResolver

CAMPUS_ID = 6
CAMPUS_NAME = "Serra"
GROUP_ID = 9  # a research group id...
INITIATIVE_ID = 500
INITIATIVE_TEAM_ID = 7001  # ...deliberately disjoint from its team id (spec 014)
PERSON_ID = 42
ARTICLE_ID = 300
ADVISORSHIP_ID = 800

SCHEMA = """
CREATE TABLE research_groups (id INTEGER PRIMARY KEY, campus_id INTEGER);
CREATE TABLE initiatives (id INTEGER PRIMARY KEY, parent_id INTEGER);
CREATE TABLE initiative_teams (initiative_id INTEGER, team_id INTEGER);
CREATE TABLE team_members (person_id INTEGER, team_id INTEGER, role_id INTEGER);
CREATE TABLE article_authors (article_id INTEGER, researcher_id INTEGER);
CREATE TABLE advisorships (id INTEGER PRIMARY KEY, student_id INTEGER, supervisor_id INTEGER);
CREATE TABLE advisorship_members (advisorship_id INTEGER, person_id INTEGER, role_name TEXT);
CREATE TABLE group_knowledge_areas (group_id INTEGER, area_id INTEGER);
CREATE TABLE entity_matches (source_record_id INTEGER, canonical_entity_type TEXT, canonical_entity_id INTEGER);
CREATE TABLE attribute_assertions (source_record_id INTEGER, canonical_entity_type TEXT, canonical_entity_id INTEGER);
CREATE TABLE entity_change_logs (source_record_id INTEGER, canonical_entity_type TEXT, canonical_entity_id INTEGER);
CREATE TABLE source_records (id INTEGER PRIMARY KEY, ingestion_run_id INTEGER);
"""


class TestExportCampusResolverSql(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.session = Session(self.engine)
        for statement in filter(None, (s.strip() for s in SCHEMA.split(";"))):
            self.session.execute(text(statement))

        # One person in one Serra research group, who also sits on an
        # initiative's own team, authored an article, and supervises an
        # advisorship. Every campus below therefore has to resolve to Serra.
        self.session.execute(
            text("INSERT INTO research_groups (id, campus_id) VALUES (:g, :c)"),
            {"g": GROUP_ID, "c": CAMPUS_ID},
        )
        self.session.execute(
            text("INSERT INTO team_members (person_id, team_id, role_id) VALUES (:p, :t, 1)"),
            {"p": PERSON_ID, "t": GROUP_ID},
        )
        self.session.execute(
            text("INSERT INTO initiatives (id, parent_id) VALUES (:i, NULL)"),
            {"i": INITIATIVE_ID},
        )
        self.session.execute(
            text("INSERT INTO initiative_teams (initiative_id, team_id) VALUES (:i, :t)"),
            {"i": INITIATIVE_ID, "t": INITIATIVE_TEAM_ID},
        )
        self.session.execute(
            text("INSERT INTO team_members (person_id, team_id, role_id) VALUES (:p, :t, 1)"),
            {"p": PERSON_ID, "t": INITIATIVE_TEAM_ID},
        )
        self.session.execute(
            text("INSERT INTO article_authors (article_id, researcher_id) VALUES (:a, :p)"),
            {"a": ARTICLE_ID, "p": PERSON_ID},
        )
        self.session.execute(
            text("INSERT INTO advisorships (id, student_id, supervisor_id) VALUES (:a, NULL, :p)"),
            {"a": ADVISORSHIP_ID, "p": PERSON_ID},
        )
        self.session.execute(
            text("INSERT INTO initiatives (id, parent_id) VALUES (:a, NULL)"),
            {"a": ADVISORSHIP_ID},
        )
        self.session.execute(
            text(
                "INSERT INTO advisorship_members (advisorship_id, person_id, role_name) "
                "VALUES (:a, :p, 'Supervisor')"
            ),
            {"a": ADVISORSHIP_ID, "p": PERSON_ID},
        )

        campus_ctrl = MagicMock()
        campus_ctrl.get_all.return_value = [{"id": CAMPUS_ID, "name": CAMPUS_NAME}]
        self.resolver = ExportCampusResolver(self.session, campus_ctrl)

    def tearDown(self):
        self.session.close()

    def test_article_resolves_campus_through_its_authors(self):
        campus = self.resolver.get_campus("article", ARTICLE_ID)
        self.assertIsNotNone(
            campus, "article campus came back None — the author->group->campus query broke"
        )
        self.assertEqual(campus["name"], CAMPUS_NAME)

    def test_initiative_resolves_campus_through_its_team_members(self):
        campus = self.resolver.get_campus("initiative", INITIATIVE_ID)
        self.assertIsNotNone(
            campus,
            "initiative campus came back None even though a team member belongs "
            "to a research group — the team id is disjoint from research_groups.id "
            "by design since spec 014, so resolution must go through the members",
        )
        self.assertEqual(campus["name"], CAMPUS_NAME)

    def test_advisorship_resolves_campus_through_its_members(self):
        campus = self.resolver.get_campus("advisorship", ADVISORSHIP_ID)
        self.assertIsNotNone(
            campus, "advisorship campus came back None despite its supervisor's group"
        )
        self.assertEqual(campus["name"], CAMPUS_NAME)

    def test_researcher_still_resolves(self):
        """Guards the one path that was already working, so a fix to the others
        cannot quietly break it."""
        campus = self.resolver.get_campus("researcher", PERSON_ID)
        self.assertIsNotNone(campus)
        self.assertEqual(campus["name"], CAMPUS_NAME)


if __name__ == "__main__":
    unittest.main()
