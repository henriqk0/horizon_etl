from typing import Any, Dict, Optional

import pandas as pd
from eo_lib import Initiative, InitiativeController, PersonController, TeamController
from loguru import logger
from research_domain import (  # CampusController,; KnowledgeAreaController,; Workaround: Import directly from controllers module since not exported in __init__
    ResearchGroupController,
)
from research_domain.controllers.controllers import (  # FellowshipController,
    AdvisorshipController,
)
from research_domain.domain.entities import Advisorship
from sqlalchemy import text

from src.core.logic.entity_manager import EntityManager
from src.core.logic.initiative_handlers import (
    AdvisorshipHandler,
    StandardProjectHandler,
)
from src.core.logic.initiative_identity import get_existing_initiative_identity
from src.core.logic.initiative_linker import InitiativeLinker
from src.core.logic.person_matcher import PersonMatcher
from src.core.logic.team_synchronizer import TeamSynchronizer
from src.tracking.recorder import tracking_recorder


class ProjectLoader:
    """
    Orchestrates the loading of project initiatives from external sources.
    Delegates specific tasks to specialized handlers, managers, and linkers.
    """

    def __init__(self, mapping_strategy):
        self.mapping_strategy = mapping_strategy

        # Controllers
        self.controller = InitiativeController()
        self.person_controller = PersonController()
        self.team_controller = TeamController()
        self.rg_controller = ResearchGroupController()
        self.adv_controller = AdvisorshipController()

        # Service/Logic Classes
        self.entity_manager = EntityManager(self.controller, self.person_controller)
        self.person_matcher = PersonMatcher(self.person_controller)

        # Initialize Roles and Cache
        roles_cache = self.entity_manager.ensure_roles()

        self.team_synchronizer = TeamSynchronizer(self.team_controller, roles_cache)

        self.linker = InitiativeLinker(
            initiative_controller=self.controller,
            rg_controller=self.rg_controller,
            team_controller=self.team_controller,
            person_matcher=self.person_matcher,
            team_synchronizer=self.team_synchronizer,
            entity_manager=self.entity_manager,
        )

        # Handlers registry
        self.handlers = {
            Initiative: StandardProjectHandler(self.controller),
            Advisorship: AdvisorshipHandler(
                self.controller, self.person_matcher, self.entity_manager
            ),
        }

        # Ensure base environment
        self.initiative_type = self.entity_manager.ensure_initiative_type(
            "Research Project"
        )
        self.org_id = self.entity_manager.ensure_organization()

    def process_file(self, file_path: str) -> None:
        """
        Reads an Excel file and orchestrates the UPSERT logic across handlers and linkers.
        """
        logger.info(f"Processing Projects from: {file_path}")

        try:
            df = pd.read_excel(file_path)
            df = df.fillna("")
        except Exception as e:
            logger.error(f"Failed to read Excel file {file_path}: {e}")
            return

        records = df.to_dict("records")
        self.process_records(records, source_file=file_path)

    def process_records(
        self, records: list[Dict[str, Any]], source_file: Optional[str] = None
    ) -> None:
        """
        Maps a list of raw dictionary records and orchestrates the UPSERT logic across handlers and linkers.
        """
        logger.info("Fetching existing initiatives for UPSERT...")
        existing_initiatives = self.controller.get_all()
        existing_by_name = {
            init.name: init
            for init in existing_initiatives
            if getattr(init, "name", None)
        }
        existing_by_identity = {}
        for init in existing_initiatives:
            identity = get_existing_initiative_identity(init)
            if identity:
                existing_by_identity[identity] = init

        self.person_matcher.preload_cache()
        initial_persons_count = len(self.person_matcher._persons_cache)

        stats = {"created": 0, "updated": 0, "skipped": 0, "teams": 0}

        for row_dict in records:
            try:
                self._process_row(
                    row_dict,
                    existing_by_name,
                    existing_by_identity,
                    stats,
                    source_file=source_file,
                )
            except Exception as e:
                logger.warning(f"Skipping row due to error: {e}")
                stats["skipped"] += 1
                self._rollback_session()

        new_persons_count = (
            len(self.person_matcher._persons_cache) - initial_persons_count
        )
        logger.info(
            f"Ingestion complete: {stats['created']} created, {stats['updated']} updated, "
            f"{stats['skipped']} skipped | {stats['teams']} teams, {new_persons_count} new persons"
        )

    def recalculate_all_parent_statuses(self) -> None:
        """
        Recalculates start_date, end_date, and status for ALL parent research projects
        based on the persisted advisorships in the database.
        This fixes orphans and ensures consistency across all years.
        """
        logger.info(
            "Recalculating dates and status for all parent projects from Database..."
        )

        from datetime import date, datetime

        from sqlalchemy import text

        session = self.controller._service._repository._session

        # Aggregate dates for all parents that have advisorships
        query = text(
            """
            SELECT
                i.parent_id,
                MIN(i.start_date) as min_start,
                MAX(i.end_date) as max_end
            FROM advisorships a
            JOIN initiatives i ON a.id = i.id
            WHERE i.parent_id IS NOT NULL
            GROUP BY i.parent_id
        """
        )

        results = session.execute(query).fetchall()

        processed_count = 0
        updated_count = 0

        def ensure_datetime(val):
            if not val:
                return None
            if isinstance(val, (datetime, date)):
                return val
            if isinstance(val, str):
                try:
                    # Attempt generic ISO
                    return datetime.fromisoformat(val)
                except ValueError:
                    pass
                try:
                    # Attempt common SQL format
                    return datetime.strptime(val, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    pass
                try:
                    return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            return None

        for row in results:
            parent_id = row.parent_id
            min_start = ensure_datetime(row.min_start)
            max_end = ensure_datetime(row.max_end)

            if not parent_id:
                continue

            processed_count += 1

            # Determine status
            status = "Unknown"  # noqa: F841
            new_status = "Active"  # noqa: F841
            if max_end:
                # Check if max_end is in the past
                # Ensure max_end is comparable (datetime)
                target_date = max_end
                if hasattr(max_end, "date"):  # datetime object
                    target_date = max_end
                elif isinstance(max_end, str):
                    try:
                        target_date = datetime.fromisoformat(max_end)
                    except Exception:
                        pass

                if isinstance(target_date, datetime):
                    if target_date < datetime.now():
                        new_status = "Concluded"  # noqa: F841
                elif hasattr(target_date, "year"):  # date object
                    if target_date < datetime.now().date():
                        new_status = "Concluded"  # noqa: F841

            # Fetch parent initiative to check if update is needed
            parent = self.controller.get_by_id(parent_id)
            if not parent:
                continue

            # Check if any change is needed
            # Note: We need to handle potential None/types mismatch for comparison or just update
            # Since this is a bulk fix operation, we can just update if distinct

            needs_update = False

            # Non-destructive update for start_date: only if earlier than current
            if min_start and (not parent.start_date or min_start < parent.start_date):
                parent.start_date = min_start
                needs_update = True

            # Non-destructive update for end_date: only if later than current
            if max_end and (not parent.end_date or max_end > parent.end_date):
                parent.end_date = max_end
                needs_update = True

            # Recalculate status based on the RESULTING end_date (if it was "Unknown" or "Active/Concluded")
            if parent.end_date:
                # Map Concluded/Active based on time
                # We skip updating status if it's something like "Recusado" or "Salvo"
                if parent.status in ["Unknown", "Active", "Concluded", "Aprovado"]:
                    calculated_status = "Active"
                    if parent.end_date < datetime.now():
                        calculated_status = "Concluded"

                    if parent.status != calculated_status:
                        parent.status = calculated_status
                        needs_update = True

            if needs_update:
                self.controller.update(parent)
                updated_count += 1

        logger.info(
            f"Recalculation complete. Processed {processed_count} parents, updated {updated_count}."
        )

    def _process_row(
        self,
        row_dict: Dict[str, Any],
        existing_by_name: Dict[str, Any],
        existing_by_identity: Dict[str, Any],
        stats: Dict[str, int],
        source_file: Optional[str] = None,
    ) -> None:
        # 1. Map to Dict
        project_data = self.mapping_strategy.map_row(row_dict)

        # 2. Validation
        if not self._is_approved(row_dict) or not project_data.get("title"):
            stats["skipped"] += 1
            return

        title = project_data["title"]
        identity_key = project_data.get("identity_key")
        model_class = project_data.get("model_class", Initiative)
        handler = self.handlers.get(model_class, self.handlers[Initiative])
        source_record = tracking_recorder.record_source_record(
            source_entity_type=(
                "advisorship" if model_class is Advisorship else "initiative"
            ),
            payload=row_dict,
            source_record_id=identity_key or title,
            source_file=source_file,
            source_path=source_file,
        )

        # 2.5 Parent Initiative Handling
        parent_id = None
        parent_initiative = None
        parent_title = project_data.get("parent_title")
        if parent_title:
            parent_identity = project_data.get("parent_identity_key")
            parent_initiative = self._resolve_existing_initiative(
                existing_by_name=existing_by_name,
                existing_by_identity=existing_by_identity,
                model_class=Initiative,
                identity_key=parent_identity,
                title=parent_title,
            )

            if not parent_initiative:
                # Create parent via Standard Handler
                logger.info(f"Creating parent Research Project: {parent_title}")

                # Ensure we have the "Research Project" type for the parent
                res_proj_type = self.entity_manager.ensure_initiative_type(
                    "Research Project"
                )

                # Initial creation without dates - will be fixed by recalculate_all_parent_statuses
                parent_initiative = self.handlers[Initiative].create_or_update(
                    project_data={
                        "title": parent_title,
                        "status": "Unknown",  # Temporary
                    },
                    existing_initiative=None,
                    initiative_type_name="Research Project",
                    initiative_type_id=res_proj_type.id,
                    organization_id=self.org_id,
                )
                self._register_existing_initiative(
                    existing_by_name=existing_by_name,
                    title=parent_title,
                    initiative=parent_initiative,
                    model_class=Initiative,
                )
                parent_identity_resolved = get_existing_initiative_identity(
                    parent_initiative
                )
                if parent_identity_resolved:
                    existing_by_identity[parent_identity_resolved] = parent_initiative

            parent_id = parent_initiative.id

        # 3. UPSERT Initiative
        existing = self._resolve_existing_initiative(
            existing_by_name=existing_by_name,
            existing_by_identity=existing_by_identity,
            model_class=model_class,
            identity_key=identity_key,
            title=title,
        )
        initiative = handler.create_or_update(
            project_data=project_data,
            existing_initiative=existing,
            initiative_type_name=self.initiative_type.name,
            initiative_type_id=self.initiative_type.id,
            organization_id=self.org_id,
            parent_id=parent_id,
        )

        if not existing:
            stats["created"] += 1
            if initiative:
                self._register_existing_initiative(
                    existing_by_name=existing_by_name,
                    title=title,
                    initiative=initiative,
                    model_class=model_class,
                )
                resolved_identity = (
                    get_existing_initiative_identity(initiative) or identity_key
                )
                if resolved_identity:
                    existing_by_identity[resolved_identity] = initiative
        else:
            stats["updated"] += 1
            if initiative:
                self._register_existing_initiative(
                    existing_by_name=existing_by_name,
                    title=title,
                    initiative=initiative,
                    model_class=model_class,
                )
                resolved_identity = (
                    get_existing_initiative_identity(initiative) or identity_key
                )
                if resolved_identity:
                    existing_by_identity[resolved_identity] = initiative

        if initiative:
            canonical_entity_type = (
                "advisorship" if model_class is Advisorship else "initiative"
            )
            tracking_recorder.record_entity_match(
                source_record_id=getattr(source_record, "id", None),
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=initiative.id,
                match_strategy="identity_key" if identity_key else "title_fallback",
                match_confidence=1.0 if identity_key else 0.7,
            )
            tracked_attrs = {
                "name": title,
                "status": project_data.get("status"),
                "description": project_data.get("description"),
                "start_date": project_data.get("start_date"),
                "end_date": project_data.get("end_date"),
                "coordinator_name": project_data.get("coordinator_name"),
                "student_names": project_data.get("student_names"),
                "researcher_names": project_data.get("researcher_names"),
            }
            tracking_recorder.record_attribute_assertions(
                source_record_id=getattr(source_record, "id", None),
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=initiative.id,
                selected_attributes=tracked_attrs,
                selection_reason="loader_selected_values",
            )
            tracking_recorder.record_change(
                source_record_id=getattr(source_record, "id", None),
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=initiative.id,
                operation="create" if not existing else "update",
                changed_fields=[
                    key
                    for key, value in tracked_attrs.items()
                    if value not in (None, [], "")
                ],
                before=(
                    {"existing_initiative_id": getattr(existing, "id", None)}
                    if existing
                    else None
                ),
                after={"initiative_id": initiative.id, **tracked_attrs},
                reason=f"{self.mapping_strategy.__class__.__name__} applied",
            )

        # 3.5 Link Advisorship members to Parent Project
        if parent_id and parent_initiative:
            self.linker.add_members_to_initiative_team(parent_initiative, project_data)

        # 4. Linkages
        if initiative:
            # Team synchronization
            self.linker.create_initiative_team(initiative, project_data)
            stats["teams"] += 1

            # Research Group linkage
            rg_name = project_data.get("research_group_name")
            if rg_name and isinstance(rg_name, str) and rg_name.strip():
                self.linker.link_research_group(
                    initiative,
                    rg_name,
                    project_data,
                    project_data.get("campus_name"),
                    self.org_id,
                )

            # Knowledge Areas / Keywords
            self.linker.associate_keyword_knowledge_areas(
                initiative, project_data, rg_name
            )

    def _resolve_existing_initiative(
        self,
        *,
        existing_by_name: Dict[str, Any],
        existing_by_identity: Dict[str, Any],
        model_class,
        identity_key: Optional[str],
        title: Optional[str],
    ) -> Optional[Any]:
        if identity_key:
            candidate = existing_by_identity.get(identity_key)
            if self._candidate_matches_model(candidate, model_class):
                return candidate

        if title:
            candidate = existing_by_name.get(title)
            if self._candidate_matches_model(candidate, model_class):
                if not self._has_conflicting_identity(candidate, identity_key):
                    return candidate

        result = self._lookup_existing_by_exact_name(title, model_class)
        if result is not None and self._has_conflicting_identity(result, identity_key):
            return None
        return result

    def _has_conflicting_identity(
        self, candidate: Optional[Any], new_identity_key: Optional[str]
    ) -> bool:
        """
        Check if a candidate initiative already has an identity from the same source
        but with a different value than the new identity_key.

        Prevents name-based fallback from merging records that belong to different
        workplans (e.g., same advisorship title but different CodPT / different student).
        """
        if not new_identity_key or candidate is None:
            return False

        existing_identity = get_existing_initiative_identity(candidate)
        if not existing_identity:
            return False

        new_prefix = (
            new_identity_key.split("|")[0]
            if "|" in new_identity_key
            else new_identity_key
        )
        existing_prefix = (
            existing_identity.split("|")[0]
            if "|" in existing_identity
            else existing_identity
        )

        if (
            new_prefix
            and new_prefix == existing_prefix
            and new_identity_key != existing_identity
        ):
            return True

        return False

    def _candidate_matches_model(self, candidate: Optional[Any], model_class) -> bool:
        if candidate is None:
            return False

        is_advisorship_candidate = self._is_advisorship_candidate(candidate)
        if model_class is Advisorship:
            return is_advisorship_candidate

        return not is_advisorship_candidate

    def _is_advisorship_candidate(self, candidate: Any) -> bool:
        if isinstance(candidate, Advisorship):
            return True

        candidate_id = getattr(candidate, "id", None)
        if not candidate_id:
            return False

        try:
            return self.adv_controller.get_by_id(candidate_id) is not None
        except Exception:
            return False

    def _lookup_existing_by_exact_name(
        self, title: Optional[str], model_class
    ) -> Optional[Any]:
        if not title:
            return None

        session = self.controller._service._repository._session
        row = session.execute(
            text("SELECT id FROM initiatives WHERE name = :name LIMIT 1"),
            {"name": title},
        ).fetchone()
        if not row:
            return None

        candidate_id = row[0]
        if model_class is Advisorship:
            try:
                return self.adv_controller.get_by_id(candidate_id)
            except Exception:
                return None

        try:
            candidate = self.controller.get_by_id(candidate_id)
        except Exception:
            return None

        if self._is_advisorship_candidate(candidate):
            return None
        return candidate

    def _register_existing_initiative(
        self,
        *,
        existing_by_name: Dict[str, Any],
        title: Optional[str],
        initiative: Any,
        model_class,
    ) -> None:
        if not title or not initiative:
            return

        current = existing_by_name.get(title)
        if current is None or self._candidate_matches_model(current, model_class):
            existing_by_name[title] = initiative

    REJECTED_STATUSES = {"recusado", "reprovado", "negado", "cancelado"}

    def _is_approved(self, row_dict: Dict[str, Any]) -> bool:
        parecer = row_dict.get("ParecerDiretoria", "Aprovado")
        if (
            isinstance(parecer, str)
            and parecer.strip()
            and parecer.strip().lower() in self.REJECTED_STATUSES
        ):
            logger.info(
                f"Skipping project '{row_dict.get('Título', 'Unknown')}' - {parecer}"
            )
            return False
        return True

    def _rollback_session(self):
        try:
            self.controller._service._repository._session.rollback()
        except Exception:
            pass
