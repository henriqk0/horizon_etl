from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text


class ExportCampusResolver:
    """Best-effort campus resolver for export payloads with 3-tier student cascade."""

    def __init__(self, session: Any, campus_ctrl: Any):
        self.session = session
        self.campus_ctrl = campus_ctrl
        self._loaded = False
        self._campus_by_id: dict[int, dict[str, Any]] = {}
        self._primary_by_entity: dict[tuple[str, int], dict[str, Any]] = {}

        # 3-Tier Student Cascade State
        self._student_level1_project_campuses: dict[int, Counter[int]] = defaultdict(
            Counter
        )
        self._student_level2_group_campuses: dict[int, Counter[int]] = defaultdict(
            Counter
        )
        self._student_level3_advisor_campuses: dict[int, Counter[int]] = defaultdict(
            Counter
        )

    def get_campus(self, entity_type: str, entity_id: Any) -> Optional[dict[str, Any]]:
        self._ensure_loaded()
        if entity_type and str(entity_type).lower() in ("student", "discente", "aluno"):
            campuses = self.get_student_campuses(entity_id)
            return dict(campuses[0]) if campuses else None

        key = self._normalize_key(entity_type, entity_id)
        if key is None:
            return None

        campus = self._primary_by_entity.get(key)
        return dict(campus) if campus else None

    def get_student_campuses(self, entity_id: Any) -> list[dict[str, Any]]:
        """
        Returns all resolved campuses for a student using 3-tier priority cascade:
        1. Projects/Editais
        2. Research Groups
        3. Main Academic Advisor
        """
        self._ensure_loaded()
        student_id = self._normalize_int(entity_id)
        if student_id is None:
            return []

        # Tier 1: Projects / Editais
        c1 = self._student_level1_project_campuses.get(student_id)
        if c1:
            return self._order_campuses(c1)

        # Tier 2: Research Groups
        c2 = self._student_level2_group_campuses.get(student_id)
        if c2:
            return self._order_campuses(c2)

        # Tier 3: Main Academic Advisor
        c3 = self._student_level3_advisor_campuses.get(student_id)
        if c3:
            return self._order_campuses(c3)

        return []

    def get_student_resolution_audit(self, entity_id: Any) -> dict[str, Any]:
        """Returns provenance audit metadata for student campus resolution."""
        self._ensure_loaded()
        student_id = self._normalize_int(entity_id)
        if student_id is None:
            return {"resolved_via": "unresolved", "confidence": "low"}

        if (
            student_id in self._student_level1_project_campuses
            and self._student_level1_project_campuses[student_id]
        ):
            return {"resolved_via": "project", "confidence": "high"}

        if (
            student_id in self._student_level2_group_campuses
            and self._student_level2_group_campuses[student_id]
        ):
            return {"resolved_via": "research_group", "confidence": "medium"}

        if (
            student_id in self._student_level3_advisor_campuses
            and self._student_level3_advisor_campuses[student_id]
        ):
            return {"resolved_via": "main_advisor", "confidence": "low"}

        return {"resolved_via": "unresolved", "confidence": "low"}

    def _order_campuses(self, counter: Counter[int]) -> list[dict[str, Any]]:
        if not counter:
            return []
        ordered_ids = sorted(
            counter.items(),
            key=lambda item: (
                -item[1],
                self._campus_by_id[item[0]]["name"],
                item[0],
            ),
        )
        return [dict(self._campus_by_id[cid]) for cid, _ in ordered_ids]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        self._campus_by_id = self._load_campuses()
        if not self._campus_by_id:
            return

        campus_counts: dict[tuple[str, int], Counter[int]] = defaultdict(Counter)

        def add_campus(
            entity_type: str, entity_id: Any, campus_id: Any, weight: int = 1
        ):
            key = self._normalize_key(entity_type, entity_id)
            normalized_campus_id = self._normalize_int(campus_id)
            if key is None or normalized_campus_id is None:
                return
            if normalized_campus_id not in self._campus_by_id:
                return
            campus_counts[key][normalized_campus_id] += max(weight, 1)

        for campus_id in self._campus_by_id:
            add_campus("campus", campus_id, campus_id)

        for row in self._run_query(
            """
            SELECT id AS entity_id, campus_id, 1 AS weight
            FROM research_groups
            WHERE campus_id IS NOT NULL
            """,
        ):
            add_campus(
                "research_group",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        # An initiative directly attached to a research group's own team
        # inherits that group's campus. This is now the rare case: spec 014
        # gave initiative teams ids disjoint from research_groups.id on
        # purpose (forcing teams.id == initiatives.id had merged unrelated
        # initiative members into every group's roster), so this join stops
        # matching for initiatives that own their team. Kept because it is
        # still the most direct evidence whenever it does match.
        for row in self._run_query("""
            SELECT it.initiative_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM initiative_teams it
            JOIN research_groups rg ON rg.id = it.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY it.initiative_id, rg.campus_id
            """):
            add_campus(
                "initiative",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        # Post-spec-014 path: reach the campus through the PEOPLE on the
        # initiative's team and the research groups they belong to. Without
        # this every initiative resolved to no campus at all, which silently
        # emptied projects and publications out of any campus-filtered view.
        for row in self._run_query("""
            SELECT it.initiative_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM initiative_teams it
            JOIN team_members itm ON itm.team_id = it.team_id
            JOIN team_members rgm ON rgm.person_id = itm.person_id
            JOIN research_groups rg ON rg.id = rgm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY it.initiative_id, rg.campus_id
            """):
            add_campus(
                "initiative",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        # Advisorships inherit from their sponsoring project's team, routed
        # through its members for the same reason as above.
        for row in self._run_query("""
            SELECT a.id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM advisorships a
            JOIN initiatives i ON i.id = a.id
            JOIN initiative_teams it ON it.initiative_id = COALESCE(i.parent_id, i.id)
            JOIN team_members itm ON itm.team_id = it.team_id
            JOIN team_members rgm ON rgm.person_id = itm.person_id
            JOIN research_groups rg ON rg.id = rgm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY a.id, rg.campus_id
            """):
            add_campus(
                "advisorship",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        # Most advisorships have no sponsoring project at all (only SigPesq
        # supplies that link), so the query above cannot reach them. Their own
        # supervisor and student are then the available campus evidence.
        for row in self._run_query("""
            SELECT am.advisorship_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM advisorship_members am
            JOIN team_members rgm ON rgm.person_id = am.person_id
            JOIN research_groups rg ON rg.id = rgm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY am.advisorship_id, rg.campus_id
            """):
            add_campus(
                "advisorship",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query("""
            SELECT tm.person_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM team_members tm
            JOIN research_groups rg ON rg.id = tm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY tm.person_id, rg.campus_id
            """):
            add_campus(
                "researcher",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )
            # Student Level 2: Research Groups
            p_id = self._normalize_int(row["entity_id"])
            c_id = self._normalize_int(row["campus_id"])
            if p_id and c_id and c_id in self._campus_by_id:
                self._student_level2_group_campuses[p_id][c_id] += max(
                    int(row["weight"]), 1
                )

        # Student Level 1: Projects / Editais (initiative teams & advisorship initiatives)
        for row in self._run_query("""
            SELECT tm.person_id AS student_id, rg.campus_id, COUNT(*) AS weight
            FROM team_members tm
            JOIN initiative_teams it ON it.team_id = tm.team_id
            JOIN research_groups rg ON rg.id = it.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY tm.person_id, rg.campus_id
            """):
            p_id = self._normalize_int(row["student_id"])
            c_id = self._normalize_int(row["campus_id"])
            if p_id and c_id and c_id in self._campus_by_id:
                self._student_level1_project_campuses[p_id][c_id] += max(
                    int(row["weight"]), 1
                )

        for row in self._run_query("""
            SELECT aa.article_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM article_authors aa
            JOIN team_members tm ON tm.person_id = aa.researcher_id
            JOIN research_groups rg ON rg.id = tm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY aa.article_id, rg.campus_id
            """):
            add_campus(
                "article",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query("""
            SELECT gka.area_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM group_knowledge_areas gka
            JOIN research_groups rg ON rg.id = gka.group_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY gka.area_id, rg.campus_id
            """):
            add_campus(
                "knowledge_area",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        primary_from_direct = self._build_primary_map(campus_counts)

        # Student Level 3: Main Academic Advisor
        # Find student-supervisor links
        advisor_pairs = self._run_query("""
            SELECT am_std.person_id AS student_id, am_sup.person_id AS supervisor_id
            FROM advisorship_members am_std
            JOIN advisorship_members am_sup ON am_sup.advisorship_id = am_std.advisorship_id
            WHERE am_std.role_name IN ('Student', 'Bolsista', 'Orientando')
              AND am_sup.role_name IN ('Supervisor', 'Coordinator', 'Orientador', 'Leader')
            """)
        if not advisor_pairs:
            advisor_pairs = self._run_query("""
                SELECT student_id, supervisor_id
                FROM advisorships
                WHERE student_id IS NOT NULL AND supervisor_id IS NOT NULL
                """)

        for row in advisor_pairs:
            s_id = self._normalize_int(row.get("student_id"))
            sup_id = self._normalize_int(row.get("supervisor_id"))
            if s_id and sup_id:
                sup_campus = primary_from_direct.get(("researcher", sup_id))
                if sup_campus and sup_campus.get("id") in self._campus_by_id:
                    self._student_level3_advisor_campuses[s_id][sup_campus["id"]] += 1

        for row in self._run_query("""
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM entity_matches
            UNION ALL
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM attribute_assertions
            UNION ALL
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM entity_change_logs
            WHERE source_record_id IS NOT NULL
            """):
            entity_key = self._normalize_key(
                row["canonical_entity_type"], row["canonical_entity_id"]
            )
            if entity_key is None:
                continue
            campus = primary_from_direct.get(entity_key)
            if campus:
                add_campus("source_record", row["source_record_id"], campus["id"])

        primary_with_sources = self._build_primary_map(campus_counts)

        for row in self._run_query("""
            SELECT ingestion_run_id AS entity_id, id AS source_record_id
            FROM source_records
            """):
            source_record_key = self._normalize_key(
                "source_record", row["source_record_id"]
            )
            if source_record_key is None:
                continue
            campus = primary_with_sources.get(source_record_key)
            if campus:
                add_campus("ingestion_run", row["entity_id"], campus["id"])

        self._primary_by_entity = self._build_primary_map(campus_counts)

    def _load_campuses(self) -> dict[int, dict[str, Any]]:
        try:
            campuses = self.campus_ctrl.get_all()
        except Exception as exc:
            logger.debug(f"Could not preload campuses for export resolution: {exc}")
            return {}

        campus_by_id: dict[int, dict[str, Any]] = {}
        for campus in campuses:
            campus_dict = None
            if isinstance(campus, dict):
                campus_dict = campus
            elif hasattr(campus, "to_dict"):
                try:
                    campus_dict = campus.to_dict()
                except Exception:
                    campus_dict = None

            campus_id = self._normalize_int(
                campus_dict.get("id") if campus_dict else getattr(campus, "id", None)
            )
            name = (
                campus_dict.get("name")
                if campus_dict
                else getattr(campus, "name", None)
            )
            if campus_id is None or not name:
                continue
            campus_by_id[campus_id] = {"id": campus_id, "name": name}

        return campus_by_id

    def _run_query(self, sql: str) -> list[dict[str, Any]]:
        if self.session is None:
            return []

        try:
            rows = self.session.execute(text(sql)).fetchall()
        except Exception as exc:
            # Deliberately a warning, not debug: a failing query here does not
            # raise, it just yields no campus evidence, so the export still
            # succeeds while quietly emitting entities with campus=None. A
            # typo in one of these queries ("SELECT a.id" against a FROM that
            # never aliased anything `a`) hid that way and blanked the campus
            # of every article in the export.
            logger.warning(
                "Campus export query failed — affected entities will have no "
                "campus: {}\n{}",
                exc,
                sql.strip(),
            )
            return []

        result = []
        for row in rows:
            if hasattr(row, "_mapping"):
                result.append(dict(row._mapping))
            elif isinstance(row, dict):
                result.append(row)
            else:
                try:
                    result.append(dict(row))
                except Exception:
                    continue
        return result

    def _build_primary_map(
        self, campus_counts: dict[tuple[str, int], Counter[int]]
    ) -> dict[tuple[str, int], dict[str, Any]]:
        primary: dict[tuple[str, int], dict[str, Any]] = {}
        for key, counter in campus_counts.items():
            if not counter:
                continue

            ordered = sorted(
                counter.items(),
                key=lambda item: (
                    -item[1],
                    self._campus_by_id[item[0]]["name"],
                    item[0],
                ),
            )
            primary[key] = dict(self._campus_by_id[ordered[0][0]])
        return primary

    @staticmethod
    def _normalize_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_key(
        self, entity_type: Any, entity_id: Any
    ) -> Optional[tuple[str, int]]:
        if not entity_type:
            return None

        normalized_id = self._normalize_int(entity_id)
        if normalized_id is None:
            return None

        return str(entity_type), normalized_id
