from typing import Optional

from eo_lib.controllers.organization_controller import OrganizationController
from loguru import logger
from research_domain import CampusController, ResearchGroupController

from src.core.logic.pii_anonymizer import anonymize_email, is_anonymized_email
from src.core.ports.export_sink import IExportSink


class ResearchGroupExporter:

    def __init__(self, sink: IExportSink):
        self.sink = sink
        self.rg_ctrl = ResearchGroupController()
        # Initialize controllers for enrichment
        self.campus_ctrl = CampusController()
        self.org_ctrl = OrganizationController()

    def export_all(self, output_path: str, campus_filter: Optional[str] = None) -> int:
        """
        Fetches all Research Groups, enriches them with related entity data,
        and exports them to the specified path.

        Args:
        Args:
            output_path: Destination file path.
            campus_filter: Optional name of the campus to filter by (case-insensitive).

        Returns:
            The number of exported groups with an unresolved institutional
            affiliation (missing/unknown campus or organization) — see
            specs/011-research-group-institutional-filtering.
        """
        logger.info("Fetching all Research Groups from database...")
        try:
            # 1. Fetch main entities
            all_groups = self.rg_ctrl.get_all()

            if not all_groups:
                logger.warning("No Research Groups found to export.")
                self.sink.export([], output_path)
                return 0

            # Filter by Campus if requested
            groups = all_groups
            if campus_filter:
                logger.info(f"Filtering groups for campus: {campus_filter}")
                # resolve campus id
                all_campuses_lookup = self.campus_ctrl.get_all()
                target_campus = next(
                    (
                        c
                        for c in all_campuses_lookup
                        if c.name.lower() == campus_filter.lower()
                    ),
                    None,
                )

                if not target_campus:
                    logger.warning(
                        f"Campus '{campus_filter}' not found. Exporting 0 groups."
                    )
                    groups = []
                else:
                    groups = [g for g in all_groups if g.campus_id == target_campus.id]
                    logger.info(
                        f"Filtered {len(groups)} groups for campus {target_campus.name}"
                    )

            logger.info(f"Found {len(groups)} groups. Preparing enrichment maps...")

            # 2. Fetch auxiliary data for mapping (Optimization to avoid N+1 queries if not lazy loaded efficiently)
            # Fetching all might be heavy if tables are huge, but for now assuming manageable size
            all_orgs = self.org_ctrl.get_all()
            org_map = {org.id: {"id": org.id, "name": org.name} for org in all_orgs}

            all_campuses = self.campus_ctrl.get_all()
            campus_map = {c.id: {"id": c.id, "name": c.name} for c in all_campuses}

            if not campus_map and any(getattr(g, "campus_id", None) for g in groups):
                logger.warning(
                    "Research groups reference campus ids but the campuses table is "
                    "empty ({} groups); exported 'campus' values will be null.",
                    len(groups),
                )

            logger.info("Enriching data...")
            enriched_data = []
            unresolved_count = 0

            for group in groups:
                # Base serialization
                group_dict = group.to_dict()

                # Enrich Organization — only assign a real, resolvable
                # organization. Never fall back to an arbitrary or fabricated
                # value: a group's institutional affiliation must be its own
                # or explicitly marked unresolved (spec 011 FR-004/FR-006).
                campus_entry = campus_map.get(group.campus_id)
                org_entry = org_map.get(group.organization_id)

                group_dict["campus"] = campus_entry
                group_dict["organization"] = org_entry

                if not campus_entry or not org_entry:
                    group_dict["unresolved_institutional_affiliation"] = True
                    unresolved_count += 1

                # Enrich Knowledge Areas
                # Assuming lazy loading works (attached session or eager load)
                if hasattr(group, "knowledge_areas"):
                    # Include ID alongside Name
                    group_dict["knowledge_areas"] = [
                        {"id": ka.id, "name": ka.name} for ka in group.knowledge_areas
                    ]

                # Enrich Members and Leaders
                if hasattr(group, "members"):
                    members_list = []
                    leaders_list = []
                    seen_members = set()

                    for tm in group.members:
                        # tm is a TeamMember association object
                        person_name = tm.person.name if tm.person else "Unknown"
                        # Check distinct attributes or use Person ID if available
                        person_id = tm.person.id if tm.person else person_name

                        # Use lattes_url if exists, ensure access is safe
                        lattes = (
                            getattr(tm.person, "lattes_url", None)
                            if tm.person
                            else None
                        )

                        # Fetch Emails
                        # emails is a relationship to PersonEmail objects
                        email_list = []
                        if (
                            tm.person
                            and hasattr(tm.person, "emails")
                            and tm.person.emails
                        ):
                            email_list = [
                                (
                                    anonymize_email(e.email)
                                    if not is_anonymized_email(e.email)
                                    else e.email
                                )
                                for e in tm.person.emails
                            ]

                        role_name = tm.role.name if tm.role else "Member"

                        member_obj = {
                            "id": person_id,
                            "name": person_name,
                            "role": role_name,
                            "lattes_url": lattes,
                            "emails": email_list,
                            "start_date": (
                                tm.start_date.strftime("%Y-%m-%d")
                                if tm.start_date
                                else None
                            ),
                            "end_date": (
                                tm.end_date.strftime("%Y-%m-%d")
                                if tm.end_date
                                else None
                            ),
                        }

                        # Deduplicate members list based on person_id
                        if person_id not in seen_members:
                            members_list.append(member_obj)
                            seen_members.add(person_id)

                        # Check for leader logic (flexible check)
                        if role_name and (
                            "leader" in role_name.lower()
                            or "líder" in role_name.lower()
                        ):
                            # Check if we have already added a leader with the same id
                            is_already_leader = any(
                                leader["id"] == member_obj["id"]
                                for leader in leaders_list
                            )

                            if not is_already_leader:
                                leaders_list.append(member_obj)

                    group_dict["members"] = members_list
                    group_dict["leaders"] = leaders_list

                enriched_data.append(group_dict)

            # Export enriched data
            self.sink.export(enriched_data, output_path)

            logger.info(f"Export completed successfully to {output_path}")
            if unresolved_count:
                logger.warning(
                    "{} of {} research group(s) exported with unresolved "
                    "institutional affiliation (missing/unknown campus or organization)",
                    unresolved_count,
                    len(groups),
                )

            return unresolved_count

        except Exception as e:
            logger.error(f"Error during export: {e}")
            raise e
