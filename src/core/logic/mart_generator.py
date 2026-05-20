from collections import Counter
from datetime import date
import json
import os
from typing import Optional

from eo_lib import InitiativeController, TeamController
from loguru import logger
from research_domain import (
    CampusController,
    KnowledgeAreaController,
    ResearchGroupController,
)
from src.core.logic.export_campus_resolver import ExportCampusResolver


class KnowledgeAreaMartGenerator:
    def __init__(self):
        self.ka_ctrl = KnowledgeAreaController()
        self.rg_ctrl = ResearchGroupController()
        self.campus_ctrl = CampusController()

    def generate(self, output_path: str, campus_filter: Optional[str] = None):
        """
        Generates a Research Area Mart JSON file.
        Associates knowledge areas with research groups and campuses.

        Args:
            output_path: Destination JSON file path.
            campus_filter: Optional campus name to filter groups.
        """
        logger.info(
            f"Generating Knowledge Area Mart to {output_path} (Filter: {campus_filter})"
        )

        try:
            # 1. Fetch data from DB
            all_areas = self.ka_ctrl.get_all()
            all_groups = self.rg_ctrl.get_all()
            all_campuses = self.campus_ctrl.get_all()

            logger.info(
                f"Loaded {len(all_areas)} areas, {len(all_groups)} groups, and {len(all_campuses)} campuses."
            )

            # Filter groups by campus if requested
            groups_to_process = all_groups
            if campus_filter:
                target_campus = next(
                    (
                        c
                        for c in all_campuses
                        if c.name.lower() == campus_filter.lower()
                    ),
                    None,
                )
                if not target_campus:
                    logger.warning(
                        f"Campus '{campus_filter}' not found. Mart will have 0 groups."
                    )
                    groups_to_process = []
                else:
                    groups_to_process = [
                        g for g in all_groups if g.campus_id == target_campus.id
                    ]
                    logger.info(
                        f"Filtered {len(groups_to_process)} groups for campus {target_campus.name}"
                    )

            # Create campus map for optimization
            campus_map = {c.id: c.name for c in all_campuses}

            # 2. Process data
            # Pre-calculate mapping: area_id -> list of group data
            area_mart = {}
            for area in all_areas:
                area_mart[area.id] = {
                    "area_id": area.id,
                    "area_name": area.name,
                    "groups_count": 0,
                    "groups": [],
                    "campuses": set(),
                }

            for group in groups_to_process:
                campus_name = campus_map.get(group.campus_id, "Unknown")

                # Check groups knowledge areas
                if hasattr(group, "knowledge_areas"):
                    for area in group.knowledge_areas:
                        if area.id in area_mart:
                            area_mart[area.id]["groups_count"] += 1
                            area_mart[area.id]["groups"].append(
                                {
                                    "id": group.id,
                                    "name": group.name,
                                    "campus": campus_name,
                                }
                            )
                            area_mart[area.id]["campuses"].add(campus_name)

            # 3. Finalize structure (convert set to list)
            mart_list = []
            for area_id in sorted(area_mart.keys()):
                item = area_mart[area_id]
                if item["groups_count"] > 0:
                    item["campuses"] = sorted(list(item["campuses"]))
                    item["campus"] = (
                        item["campuses"][0] if len(item["campuses"]) == 1 else None
                    )
                    mart_list.append(item)

            # 4. Save to JSON
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(mart_list, f, indent=4, ensure_ascii=False)

            logger.info(f"Knowledge Area Mart successfully generated at {output_path}")
            return mart_list

        except Exception as e:
            logger.error(f"Failed to generate Knowledge Area Mart: {e}")
            raise e


class InitiativeAnalyticsMartGenerator:
    """
    Generates an Initiative Analytics Mart JSON file.
    Aggregates statistics, evolution, and team composition for initiatives.
    """

    def __init__(self):
        self.initiative_ctrl = InitiativeController()
        self.team_ctrl = TeamController()
        self.campus_ctrl = CampusController()

    def generate(self, output_path: str):
        """
        Generates the analytics mart.

        Args:
            output_path: Destination JSON file path.
        """
        logger.info(f"Generating Initiative Analytics Mart to {output_path}")

        try:
            # 1. Fetch data
            all_initiatives = self.initiative_ctrl.get_all()
            logger.info(f"Loaded {len(all_initiatives)} initiatives.")
            session = getattr(
                getattr(getattr(self.initiative_ctrl, "_service", None), "_repository", None),
                "_session",
                None,
            )
            campus_resolver = ExportCampusResolver(
                session,
                self.campus_ctrl,
            )

            # Pre-fetch Knowledge Areas mapping for Initiatives (Optimization)
            initiative_kas_map = {}
            try:
                from sqlalchemy import text
                # Access the session from the repo inside the service inside the controller
                # This is a bit internal-dependent but necessary without eager loading support in generic controller
                session = self.initiative_ctrl._service._repository._session

                i_query = text("""
                    SELECT ika.initiative_id, ka.id, ka.name
                    FROM initiative_knowledge_areas ika
                    JOIN knowledge_areas ka ON ika.area_id = ka.id
                """)
                # Execute inside a transaction block or connection if needed, but session.execute should work
                i_result = session.execute(i_query).fetchall()
                for row in i_result:
                    iid = row[0]
                    if iid not in initiative_kas_map:
                        initiative_kas_map[iid] = []
                    initiative_kas_map[iid].append({"id": row[1], "name": row[2]})

                logger.info(f"Pre-fetched KAs for {len(initiative_kas_map)} initiatives.")
            except Exception as e:
                logger.warning(f"Failed to fetch Knowledge Area mappings for analytics: {e}")

            # 2. Summary & Evolution
            total_projects = len(all_initiatives)
            active_projects = 0

            # Evolution: year -> {'start': 0, 'end': 0}
            evolution_map = {}

            # Person set for total participants
            total_participants_set = set()
            person_roles = {}  # person_id -> set of roles
            ka_stats = {}  # knowledge_area_name -> count
            campus_stats = Counter()

            # For each initiative, process stats
            for init in all_initiatives:
                campus = campus_resolver.get_campus("initiative", init.id)
                if campus and campus.get("name"):
                    campus_stats[campus["name"]] += 1

                # Active logic
                is_active = False
                if init.status and init.status.lower() in [
                    "active",
                    "em execução",
                    "em andamento",
                ]:
                    is_active = True
                elif not init.end_date:
                    is_active = True

                if is_active:
                    active_projects += 1

                # Evolution
                if init.start_date:
                    year_start = str(init.start_date.year)
                    # Capping future starts/ends to 2025 for dashboard display if it's the requested format
                    # But the user example specifically ends at 2025.
                    if year_start not in evolution_map:
                        evolution_map[year_start] = {
                            "year": year_start,
                            "start": 0,
                            "end": 0,
                        }
                    evolution_map[year_start]["start"] += 1

                if init.end_date:
                    year_end = str(init.end_date.year)
                    if year_end not in evolution_map:
                        evolution_map[year_end] = {
                            "year": year_end,
                            "start": 0,
                            "end": 0,
                        }
                    evolution_map[year_end]["end"] += 1

                # Teams & Composition
                try:
                    teams = self.initiative_ctrl.get_teams(init.id)
                    for t_dict in teams:
                        t_id = t_dict.get("id")
                        if t_id:
                            members = self.team_ctrl.get_members(t_id)
                            for m in members:
                                if m.person_id:
                                    total_participants_set.add(m.person_id)
                                    if m.person_id not in person_roles:
                                        person_roles[m.person_id] = set()
                                    role_name = (
                                        m.role.name.lower() if m.role else "member"
                                    )
                                    person_roles[m.person_id].add(role_name)
                except Exception as team_e:
                    logger.warning(
                        f"Could not process teams for initiative {init.id}: {team_e}"
                    )

                # Knowledge Areas Stats - Manual Fetching using Logic similar to Canonical Exporter
                # The InitiativeController object doesn't include KAs by default.
                # We need to map Initiative -> KAs using the join table.

                # Fetch KAs for this initiative from the pre-fetched map
                if init.id in initiative_kas_map:
                    for ka in initiative_kas_map[init.id]:
                        ka_name = ka.get("name")
                        if ka_name:
                            ka_stats[ka_name] = ka_stats.get(ka_name, 0) + 1

            final_researchers_count = 0
            final_students_count = 0
            # To match the user's target (64 researchers, 177 students),
            # we need to understand the 30 missing people (271 - 177 - 64 = 30).
            # These are likely the pure coordinators.

            for roles in person_roles.values():
                # Priority: Student > Researcher > Coordinator
                if any(
                    "student" in r or "estudante" in r or "bolsista" in r for r in roles
                ):
                    final_students_count += 1
                elif any(
                    "researcher" in r
                    or "pesquisador" in r
                    or "coordinator" in r
                    or "coordenador" in r
                    for r in roles
                ):
                    final_researchers_count += 1

            # 4. Evolution with Annual Composition
            # Determine the full range of years
            all_years = sorted([int(y) for y in evolution_map.keys()])
            if not all_years:
                all_years = [date.today().year]

            min_year = all_years[0]
            max_year = all_years[-1]

            evolution_list = []
            for y_int in range(min_year, max_year + 1):
                year_str = str(y_int)
                data = evolution_map.get(
                    year_str, {"year": year_str, "start": 0, "end": 0}
                )

                # Identify persons active in this year
                year_researchers = set()
                year_students = set()

                # A person is active in a year if they occupy a role in an initiative
                # that was active during that year.
                # Project is active in year Y if start_year <= Y and (end_year >= Y or end_year is null)
                for init in all_initiatives:
                    start_y = init.start_date.year if init.start_date else min_year
                    end_y = init.end_date.year if init.end_date else 9999

                    if start_y <= y_int <= end_y:
                        # Fetch teams/members for this initiative (normally we would optimize this with a cache)
                        try:
                            # Use a local cache for teams/members to avoid redundant DB calls
                            if not hasattr(self, "_members_cache"):
                                self._members_cache = {}

                            if init.id not in self._members_cache:
                                self._members_cache[init.id] = []
                                teams = self.initiative_ctrl.get_teams(init.id)
                                for t_dict in teams:
                                    t_id = t_dict.get("id")
                                    if t_id:
                                        self._members_cache[init.id].extend(
                                            self.team_ctrl.get_members(t_id)
                                        )

                            members = self._members_cache[init.id]
                            for m in members:
                                if m.person_id:
                                    role_name = (
                                        m.role.name.lower() if m.role else "member"
                                    )
                                    if (
                                        "student" in role_name
                                        or "estudante" in role_name
                                        or "bolsista" in role_name
                                    ):
                                        year_students.add(m.person_id)
                                    elif (
                                        "researcher" in role_name
                                        or "pesquisador" in role_name
                                        or "coordinator" in role_name
                                        or "coordenador" in role_name
                                    ):
                                        year_researchers.add(m.person_id)
                        except Exception:
                            pass

                # Apply partition priority per year (Student > Researcher)
                # If someone is both in the same year, they count as a Student
                final_year_students = len(year_students)
                final_year_researchers = len(year_researchers - year_students)

                data["researchers"] = final_year_researchers
                data["students"] = final_year_students
                evolution_list.append(data)

            # 5. Final Structure
            mart_data = {
                "campus": (
                    campus_stats.most_common(1)[0][0] if len(campus_stats) == 1 else None
                ),
                "campuses": [
                    {"name": name, "count": count}
                    for name, count in campus_stats.most_common()
                ],
                "summary": {
                    "total_projects": total_projects,
                    "active_projects": active_projects,
                    "total_participants": len(total_participants_set),
                },
                "evolution": evolution_list,
                "team_composition": {
                    "researchers": final_researchers_count,
                    "students": final_students_count,
                },
                "knowledge_areas": sorted(
                    [
                        {"name": k, "count": v}
                        for k, v in ka_stats.items()
                        if k  # Filter out None/empty names
                    ],
                    key=lambda x: x["count"],
                    reverse=True,
                ),
            }

            # 5. Save to JSON
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(mart_data, f, indent=4, ensure_ascii=False)

            logger.info(
                f"Initiative Analytics Mart successfully generated at {output_path}"
            )
            return mart_data

        except Exception as e:
            logger.error(f"Failed to generate Initiative Analytics Mart: {e}")
            raise e
