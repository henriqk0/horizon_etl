from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text


class ExportCampusResolver:
    """Best-effort campus resolver for export payloads."""

    def __init__(self, session: Any, campus_ctrl: Any):
        self.session = session
        self.campus_ctrl = campus_ctrl
        self._loaded = False
        self._campus_by_id: dict[int, dict[str, Any]] = {}
        self._primary_by_entity: dict[tuple[str, int], dict[str, Any]] = {}

    def get_campus(self, entity_type: str, entity_id: Any) -> Optional[dict[str, Any]]:
        self._ensure_loaded()
        key = self._normalize_key(entity_type, entity_id)
        if key is None:
            return None

        campus = self._primary_by_entity.get(key)
        return dict(campus) if campus else None

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

        for row in self._run_query(
            """
            SELECT it.initiative_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM initiative_teams it
            JOIN research_groups rg ON rg.id = it.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY it.initiative_id, rg.campus_id
            """
        ):
            add_campus(
                "initiative",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query(
            """
            SELECT a.id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM advisorships a
            JOIN initiatives i ON i.id = a.id
            JOIN initiative_teams it ON it.initiative_id = COALESCE(i.parent_id, i.id)
            JOIN research_groups rg ON rg.id = it.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY a.id, rg.campus_id
            """
        ):
            add_campus(
                "advisorship",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query(
            """
            SELECT tm.person_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM team_members tm
            JOIN research_groups rg ON rg.id = tm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY tm.person_id, rg.campus_id
            """
        ):
            add_campus(
                "researcher",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query(
            """
            SELECT aa.article_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM article_authors aa
            JOIN team_members tm ON tm.person_id = aa.researcher_id
            JOIN research_groups rg ON rg.id = tm.team_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY aa.article_id, rg.campus_id
            """
        ):
            add_campus(
                "article",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        for row in self._run_query(
            """
            SELECT gka.area_id AS entity_id, rg.campus_id, COUNT(*) AS weight
            FROM group_knowledge_areas gka
            JOIN research_groups rg ON rg.id = gka.group_id
            WHERE rg.campus_id IS NOT NULL
            GROUP BY gka.area_id, rg.campus_id
            """
        ):
            add_campus(
                "knowledge_area",
                row["entity_id"],
                row["campus_id"],
                row["weight"],
            )

        primary_from_direct = self._build_primary_map(campus_counts)

        for row in self._run_query(
            """
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM entity_matches
            UNION ALL
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM attribute_assertions
            UNION ALL
            SELECT source_record_id, canonical_entity_type, canonical_entity_id
            FROM entity_change_logs
            WHERE source_record_id IS NOT NULL
            """
        ):
            entity_key = self._normalize_key(
                row["canonical_entity_type"], row["canonical_entity_id"]
            )
            if entity_key is None:
                continue
            campus = primary_from_direct.get(entity_key)
            if campus:
                add_campus("source_record", row["source_record_id"], campus["id"])

        primary_with_sources = self._build_primary_map(campus_counts)

        for row in self._run_query(
            """
            SELECT ingestion_run_id AS entity_id, id AS source_record_id
            FROM source_records
            """
        ):
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
            logger.debug(f"Campus export query failed: {exc}")
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
