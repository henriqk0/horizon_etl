import json
import zipfile
from datetime import date, datetime
from pathlib import Path

from eo_lib import (
    InitiativeController,
    OrganizationController,
    PersonController,
    TeamController,
)
from eo_lib.domain.entities import Initiative
from loguru import logger
from research_domain import CampusController, ResearchGroupController
from research_domain.controllers.controllers import (
    AdvisorshipController,
    FellowshipController,
    RoleController,
)


class CanonicalDatabaseSeeder:
    """
    Seeds SQLite database tables (horizon.db) from canonical export JSONs
    when live ingestion sources are unavailable or returned zero items.
    """

    _CANONICAL_ZIP_PATTERN = "canonical_export_*.zip"

    def __init__(self):
        self.rg_ctrl = ResearchGroupController()
        self.campus_ctrl = CampusController()
        self.org_ctrl = OrganizationController()
        self.initiative_ctrl = InitiativeController()
        self.person_ctrl = PersonController()
        self.team_ctrl = TeamController()
        self.adv_ctrl = AdvisorshipController()
        self.fellowship_ctrl = FellowshipController()
        self.role_ctrl = RoleController()
        self._person_by_id: dict = {}

    def seed_research_groups_if_empty(self, export_dir: str = "data/exports") -> int:
        """
        If research_groups table in horizon.db has 0 groups with cnpq_url,
        parses research_groups_canonical.json from export_dir and populates DB.

        Organizations and campuses are seeded first from the same export target
        so that research groups keep valid foreign keys and downstream canonical
        exports can still enrich campus/organization objects (instead of writing
        nulls because the campuses/organizations tables are empty).
        Returns count of seeded research groups.
        """
        try:
            existing_groups = self.rg_ctrl.get_all()
            groups_with_url = [
                g for g in existing_groups if getattr(g, "cnpq_url", None)
            ]
            if groups_with_url:
                return 0
        except Exception as exc:
            logger.debug("Failed to query existing research groups: {}", exc)

        export_path = Path(export_dir).resolve()
        json_path = export_path / "research_groups_canonical.json"
        if not json_path.is_file():
            logger.info(
                "Canonical file {} not found; skipping DB seed.", json_path.name
            )
            return 0

        data = self._load_json(json_path)
        if not isinstance(data, list) or not data:
            return 0

        org_by_json_id = self._seed_organizations_if_empty(export_path)
        campus_by_name, campus_by_json_id = self._seed_campuses_if_empty(
            export_path, org_by_json_id, group_items=data
        )

        default_campus_id = self._first_campus_id()

        seeded_count = 0
        for item in data:
            if not isinstance(item, dict) or not item.get("name"):
                continue

            name = item["name"]
            cnpq_url = item.get("cnpq_url") or item.get("site") or item.get("url")

            campus_id = self._resolve_campus_id(item, campus_by_name)
            if campus_id is None:
                campus_id = campus_by_json_id.get(item.get("campus_id"))
            if campus_id is None:
                campus_id = item.get("campus_id")
            if campus_id is None:
                campus_id = default_campus_id
            organization_id = self._resolve_organization_id(item, org_by_json_id)
            if organization_id is None:
                organization_id = self._first_organization_id()
            if organization_id is None:
                logger.debug(
                    "No organization available to attach to restored group {}; "
                    "leaving organization_id null.",
                    name,
                )

            try:
                created = self.rg_ctrl.create_research_group(
                    name=name,
                    campus_id=campus_id,
                    organization_id=organization_id,
                    cnpq_url=cnpq_url,
                    description=item.get("description"),
                    short_name=item.get("short_name"),
                    site=item.get("site"),
                )
                seeded_count += 1
                self._record_restored_entity(
                    source_entity_type="research_group",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="research_group",
                    canonical_entity_id=getattr(created, "id", None),
                    selected_attributes={
                        "name": name,
                        "campus_id": campus_id,
                        "organization_id": organization_id,
                        "cnpq_url": cnpq_url,
                        "description": item.get("description"),
                        "short_name": item.get("short_name"),
                        "site": item.get("site"),
                    },
                    source_file=json_path.name,
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug("Group seeding skipped for {}: {}", name, exc)

        logger.info(
            "Seeded {} research groups into database from {}",
            seeded_count,
            json_path.name,
        )
        return seeded_count

    def seed_initiatives_if_empty(self, export_dir: str = "data/exports") -> int:
        """
        Restores initiatives and their teams from initiatives_canonical.json when
        the initiatives table is empty. Also seeds the prerequisite rows they
        reference (initiative types, roles, persons, teams) so the next canonical
        export keeps organization/team/description/end_date fields populated
        instead of writing nulls after a db-reset + fallback run.
        Returns count of seeded initiatives.
        """
        try:
            if self.initiative_ctrl.get_all():
                return 0
        except Exception as exc:
            logger.debug("Failed to query existing initiatives: {}", exc)
            return 0

        export_path = Path(export_dir).resolve()
        json_path = export_path / "initiatives_canonical.json"
        if not json_path.is_file():
            logger.info(
                "Canonical file {} not found; skipping initiative seed.",
                json_path.name,
            )
            return 0

        data = self._load_json(json_path)
        if not isinstance(data, list) or not data:
            return 0

        org_by_json_id = self._seed_organizations_if_empty(export_path)
        type_map = self._seed_initiative_types_if_empty(export_path)
        role_by_name = self._seed_roles_if_empty(export_path)
        person_by_json_id = self._seed_persons_if_empty(export_path)

        json_to_db: dict = {}
        seeded_count = 0
        seen_names: set = set()
        for item in data:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = item["name"]
            if name in seen_names:
                logger.debug("Skipping duplicate initiative name in export: {}", name)
                continue
            try:
                initiative = Initiative(
                    name=name,
                    status=item.get("status") or "Active",
                    description=item.get("description"),
                    start_date=self._parse_datetime(item.get("start_date")),
                    end_date=self._parse_datetime(item.get("end_date")),
                    initiative_type_id=type_map.get(item.get("initiative_type_id")),
                    organization_id=org_by_json_id.get(item.get("organization_id")),
                )
                self.initiative_ctrl.create(initiative)
                seen_names.add(name)
                json_to_db[item.get("id")] = initiative.id
                seeded_count += 1
                self._record_restored_entity(
                    source_entity_type="initiative",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="initiative",
                    canonical_entity_id=initiative.id,
                    selected_attributes={
                        "name": name,
                        "status": item.get("status") or "Active",
                        "description": item.get("description"),
                        "start_date": item.get("start_date"),
                        "end_date": item.get("end_date"),
                        "initiative_type_id": type_map.get(
                            item.get("initiative_type_id")
                        ),
                        "organization_id": org_by_json_id.get(
                            item.get("organization_id")
                        ),
                    },
                    source_file=json_path.name,
                )

                team = self.team_ctrl.create_team(
                    name=item["name"][:200], description=item.get("description")
                )
                self.initiative_ctrl.assign_team(initiative.id, team.id)
                for member in item.get("team") or []:
                    if not isinstance(member, dict):
                        continue
                    person_id = person_by_json_id.get(member.get("person_id"))
                    if person_id is None:
                        continue
                    role_name = (member.get("roles") or ["Member"])[0]
                    try:
                        self.team_ctrl.add_member(
                            team_id=team.id,
                            person_id=person_id,
                            role=role_by_name.get(role_name),
                            start_date=self._parse_datetime(member.get("start_date")),
                            end_date=self._parse_datetime(member.get("end_date")),
                        )
                    except Exception as exc:
                        logger.debug(
                            "Team member seeding skipped for initiative {}: {}",
                            name,
                            exc,
                        )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Initiative seeding skipped for {}: {}",
                    name,
                    exc,
                )

        self._reassign_parent_initiatives(data, json_to_db)
        logger.info(
            "Seeded {} initiatives into database from {}",
            seeded_count,
            json_path.name,
        )
        return seeded_count

    def seed_advisorships_if_empty(self, export_dir: str = "data/exports") -> int:
        """
        Restores advisorships (and their fellowship links) from
        advisorships_canonical.json when the advisorships table is empty.
        Returns count of seeded advisorship records.
        """
        try:
            if self.adv_ctrl.get_all():
                return 0
        except Exception as exc:
            logger.debug("Failed to query existing advisorships: {}", exc)
            return 0

        export_path = Path(export_dir).resolve()
        json_path = export_path / "advisorships_canonical.json"
        if not json_path.is_file():
            logger.info(
                "Canonical file {} not found; skipping advisorship seed.",
                json_path.name,
            )
            return 0

        data = self._load_json(json_path)
        if not isinstance(data, list) or not data:
            return 0

        self._person_by_id = {}
        self._seed_persons_if_empty(export_path)
        fellowship_map = self._seed_fellowships_if_empty(export_path)

        advisories: list = []
        for project in data:
            if not isinstance(project, dict):
                continue
            nested = project.get("advisorships")
            if isinstance(nested, list):
                advisories.extend(nested)

        seeded_count = 0
        for item in advisories:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                fellowship_id = fellowship_map.get(
                    self._nested_id(item.get("fellowship"))
                )
                student_id = item.get("student_id") or item.get("person_id")
                created = self.adv_ctrl.create_advisorship(
                    name=item["name"],
                    student_id=student_id,
                    supervisor_id=item.get("supervisor_id"),
                    fellowship_id=fellowship_id,
                    start_date=self._parse_datetime(item.get("start_date")),
                    end_date=self._parse_datetime(item.get("end_date")),
                    description=item.get("description"),
                    status=item.get("status") or "active",
                )
                parent_id = item.get("parent_id")
                if created is not None and parent_id is not None:
                    if hasattr(created, "parent_id"):
                        created.parent_id = parent_id
                        try:
                            self.adv_ctrl.update(created)
                        except Exception:
                            pass
                seeded_count += 1
                self._record_restored_entity(
                    source_entity_type="advisorship",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="advisorship",
                    canonical_entity_id=getattr(created, "id", None),
                    selected_attributes={
                        "name": item["name"],
                        "student_id": student_id,
                        "supervisor_id": item.get("supervisor_id"),
                        "fellowship_id": fellowship_id,
                        "parent_id": parent_id,
                        "start_date": item.get("start_date"),
                        "end_date": item.get("end_date"),
                        "description": item.get("description"),
                        "status": item.get("status") or "active",
                    },
                    source_file=json_path.name,
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Advisorship seeding skipped for {}: {}", item.get("name"), exc
                )
        logger.info(
            "Seeded {} advisorships into database from {}",
            seeded_count,
            json_path.name,
        )
        return seeded_count

    def _rollback_shared_session(self) -> None:
        """
        Rolls back the shared SQLAlchemy scoped_session after a flush/commit
        failure so the same session can keep serving the rest of the flow.
        Without this, a single IntegrityError (e.g. a duplicate initiative
        name) leaves the session in a pending-rollback state and every later
        query in the process raises PendingRollbackError.
        """
        try:
            from eo_lib.infrastructure import PostgresClient

            PostgresClient().get_session().rollback()
        except Exception as exc:
            logger.debug("Failed to roll back shared session: {}", exc)

    def _record_restored_entity(
        self,
        *,
        source_entity_type: str,
        payload: dict,
        source_record_id,
        canonical_entity_type: str,
        canonical_entity_id,
        selected_attributes: dict,
        source_file: str,
    ) -> None:
        """
        Writes provenance (source record + entity match + attribute assertions
        + change log) for a single canonical entity restored from export data.

        Mirrors what the live ingests log via tracking_recorder, so fallback
        runs keep the source_records / attribute_assertions / entity_change_logs
        tables populated instead of dropping to near-empty after a db-reset.

        When no ingestion run context is active (e.g. standalone seed calls),
        the recorder no-ops and returns None, which this helper tolerates.
        """
        if canonical_entity_id is None:
            return
        try:
            from src.tracking.recorder import tracking_recorder

            source_record = tracking_recorder.record_source_record(
                source_entity_type=source_entity_type,
                payload=payload,
                source_record_id=str(source_record_id) if source_record_id else None,
                source_file=source_file,
                source_path=source_file,
            )
            if source_record is None:
                return

            tracking_recorder.record_entity_match(
                source_record_id=source_record.id,
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=canonical_entity_id,
                match_strategy="canonical_restore",
                match_confidence=1.0,
            )
            tracking_recorder.record_attribute_assertions(
                source_record_id=source_record.id,
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=canonical_entity_id,
                selected_attributes=selected_attributes,
                selection_reason="canonical_restore_selected_values",
            )
            tracking_recorder.record_change(
                source_record_id=source_record.id,
                canonical_entity_type=canonical_entity_type,
                canonical_entity_id=canonical_entity_id,
                operation="create",
                changed_fields=list(selected_attributes.keys()),
                after=selected_attributes,
                reason="Restored canonical entity from export",
            )
        except Exception as exc:
            logger.debug(
                "Failed to record tracking for restored {}: {}",
                canonical_entity_type,
                exc,
            )

    @staticmethod
    def _nested_id(value) -> int:
        if isinstance(value, dict):
            return value.get("id")
        return value

    def _seed_initiative_types_if_empty(self, export_path: Path) -> dict:
        """Seeds initiative types; returns {json_id: db_id} (name-key fallback)."""
        mapping: dict = {}
        items = self._load_json(export_path / "initiative_types_canonical.json")
        if not isinstance(items, list) or not items:
            return mapping
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                created = self.initiative_ctrl.create_initiative_type(
                    name=item["name"], description=item.get("description")
                )
                new_id = (
                    created.get("id")
                    if isinstance(created, dict)
                    else getattr(created, "id", None)
                )
                if item.get("id") is not None:
                    mapping[item["id"]] = new_id
                mapping[item["name"]] = new_id
                self._record_restored_entity(
                    source_entity_type="initiative_type",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="initiative_type",
                    canonical_entity_id=new_id,
                    selected_attributes={
                        "name": item["name"],
                        "description": item.get("description"),
                    },
                    source_file="initiative_types_canonical.json",
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Initiative type seeding skipped for {}: {}",
                    item.get("name"),
                    exc,
                )
        return mapping

    def _seed_roles_if_empty(self, export_path: Path) -> dict:
        """Ensures roles referenced by initiative teams exist; returns name mapping."""
        mapping: dict = {}
        try:
            existing = self.role_ctrl.get_all()
            for role in existing:
                name = getattr(role, "name", None)
                if name:
                    mapping[name] = role
        except Exception as exc:
            logger.debug("Failed to query existing roles: {}", exc)

        initiatives = self._load_json(export_path / "initiatives_canonical.json")
        if not isinstance(initiatives, list):
            return mapping
        seen: set = set()
        for item in initiatives:
            if not isinstance(item, dict):
                continue
            for member in item.get("team") or []:
                if not isinstance(member, dict):
                    continue
                for role_name in member.get("roles") or []:
                    if role_name in mapping or role_name in seen:
                        continue
                    seen.add(role_name)
                    try:
                        mapping[role_name] = self.role_ctrl.create_role(
                            name=role_name, description=None
                        )
                        self._record_restored_entity(
                            source_entity_type="role",
                            payload={"name": role_name},
                            source_record_id=role_name,
                            canonical_entity_type="role",
                            canonical_entity_id=(
                                mapping[role_name].id
                                if hasattr(mapping[role_name], "id")
                                else getattr(mapping[role_name], "get", lambda k: None)(
                                    "id"
                                )
                            ),
                            selected_attributes={"name": role_name},
                            source_file="roles_restored_from_initiatives.json",
                        )
                    except Exception as exc:
                        self._rollback_shared_session()
                        logger.debug("Role seeding skipped for {}: {}", role_name, exc)
        return mapping

    def _seed_persons_if_empty(self, export_path: Path) -> dict:
        """Ensures persons referenced by initiatives/advisorships exist."""
        mapping: dict = {}

        def sync(person_id, person_name=None):
            key = self._nested_id(person_id)
            if key is None or key in mapping:
                return
            existing = self._get_person_by_id(key)
            if existing is not None:
                mapping[key] = existing.id
                return
            try:
                created = self.person_ctrl.create_person(
                    name=person_name or f"Person {key}", identification_id=None
                )
                mapping[key] = created.id
                self._record_restored_entity(
                    source_entity_type="person",
                    payload={"id": key, "name": person_name},
                    source_record_id=key,
                    canonical_entity_type="person",
                    canonical_entity_id=created.id,
                    selected_attributes={"name": person_name},
                    source_file="persons_restored_from_initiatives.json",
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug("Person seeding skipped for {}: {}", key, exc)

        initiatives = self._load_json(export_path / "initiatives_canonical.json")
        if isinstance(initiatives, list):
            for item in initiatives:
                if not isinstance(item, dict):
                    continue
                for member in item.get("team") or []:
                    if isinstance(member, dict):
                        sync(member.get("person_id"), member.get("person_name"))

        advisories = self._load_json(export_path / "advisorships_canonical.json")
        if isinstance(advisories, list):
            for project in advisories:
                if not isinstance(project, dict):
                    continue
                for item in project.get("advisorships") or []:
                    if not isinstance(item, dict):
                        continue
                    sync(item.get("person_id"), item.get("person_name"))
                    sync(item.get("supervisor_id"), item.get("supervisor_name"))
        return mapping

    def _get_person_by_id(self, person_id):
        if person_id in self._person_by_id:
            return self._person_by_id[person_id]
        try:
            person = self.person_ctrl.get_by_id(person_id)
        except Exception:
            person = None
        self._person_by_id[person_id] = person
        return person

    def _seed_fellowships_if_empty(self, export_path: Path) -> dict:
        """Seeds fellowships referenced by advisorships; returns {id: db_id}."""
        mapping: dict = {}
        items = self._load_json(export_path / "fellowships_canonical.json")
        if not isinstance(items, list):
            return mapping
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                created = self.fellowship_ctrl.create_fellowship(
                    name=item["name"],
                    value=float(item.get("value") or 0),
                    description=item.get("description"),
                )
                mapping[item.get("id")] = created.id
                self._record_restored_entity(
                    source_entity_type="fellowship",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="fellowship",
                    canonical_entity_id=created.id,
                    selected_attributes={
                        "name": item["name"],
                        "value": item.get("value"),
                        "description": item.get("description"),
                    },
                    source_file="fellowships_canonical.json",
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Fellowship seeding skipped for {}: {}", item.get("name"), exc
                )
        return mapping

    def _reassign_parent_initiatives(self, data: list, json_to_db: dict) -> None:
        """Sets parent_id on initiatives that reference another restored initiative."""
        for item in data:
            if not isinstance(item, dict):
                continue
            parent_json = self._nested_id(item.get("parent_id"))
            if parent_json is None:
                continue
            initiative = self.initiative_ctrl.get_by_id(json_to_db.get(item.get("id")))
            if initiative is None:
                continue
            parent_db = json_to_db.get(parent_json)
            if not parent_db:
                continue
            try:
                initiative.parent_id = parent_db
                self.initiative_ctrl.update(initiative)
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Parent reassignment skipped for {}: {}", item.get("name"), exc
                )

    @staticmethod
    def _parse_datetime(value):
        """Parses ISO/legacy datetime strings used by canonical exports."""
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            pass
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _seed_organizations_if_empty(self, export_path: Path) -> dict:
        """
        Seeds organizations from organizations_canonical.json when the
        organizations table is empty. Returns {json_id: db_id} mapping.
        """
        mapping: dict = {}
        try:
            if self.org_ctrl.get_all():
                return mapping
        except Exception as exc:
            logger.debug("Failed to query existing organizations: {}", exc)
            return mapping

        items = self._load_json(export_path / "organizations_canonical.json")
        if not isinstance(items, list):
            return mapping

        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                org = self.org_ctrl.create_organization(
                    name=item["name"],
                    description=item.get("description"),
                    short_name=item.get("short_name"),
                )
                mapping[item.get("id")] = org.id
                self._record_restored_entity(
                    source_entity_type="organization",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="organization",
                    canonical_entity_id=org.id,
                    selected_attributes={
                        "name": item["name"],
                        "description": item.get("description"),
                        "short_name": item.get("short_name"),
                    },
                    source_file="organizations_canonical.json",
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug(
                    "Organization seeding skipped for {}: {}",
                    item.get("name"),
                    exc,
                )
        return mapping

    def _seed_campuses_if_empty(
        self,
        export_path: Path,
        org_by_json_id: dict,
        group_items: list | None = None,
    ) -> tuple[dict, dict]:
        """
        Seeds campuses from campuses_canonical.json when the campuses table is
        empty. If that file is missing or empty, derives campus objects from the
        research groups' campus references so the campus table is not left empty
        (which would null every exported campus field).

        Returns (name -> db_id) and (json_id -> db_id) mappings.
        """
        mapping: dict = {}
        json_id_map: dict = {}
        try:
            if self.campus_ctrl.get_all():
                return mapping, json_id_map
        except Exception as exc:
            logger.debug("Failed to query existing campuses: {}", exc)
            return mapping, json_id_map

        items = self._load_json(export_path / "campuses_canonical.json")
        if not isinstance(items, list) or not items:
            items = self._derive_campuses_from_groups(group_items)
        if not isinstance(items, list) or not items:
            items = self._load_campuses_from_archives(export_path)

        if not isinstance(items, list):
            return mapping, json_id_map

        default_org_id = self._first_organization_id()
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            org_id = org_by_json_id.get(item.get("organization_id"))
            if org_id is None:
                org_id = default_org_id
            try:
                campus = self.campus_ctrl.create_campus(
                    name=item["name"],
                    organization_id=org_id,
                    description=item.get("description"),
                    short_name=item.get("short_name"),
                )
                mapping[item["name"]] = campus.id
                if item.get("id") is not None:
                    json_id_map[item["id"]] = campus.id
                self._record_restored_entity(
                    source_entity_type="campus",
                    payload=item,
                    source_record_id=item.get("id"),
                    canonical_entity_type="campus",
                    canonical_entity_id=campus.id,
                    selected_attributes={
                        "name": item["name"],
                        "organization_id": org_id,
                        "description": item.get("description"),
                        "short_name": item.get("short_name"),
                    },
                    source_file="campuses_canonical.json",
                )
            except Exception as exc:
                self._rollback_shared_session()
                logger.debug("Campus seeding skipped for {}: {}", item.get("name"), exc)

        return mapping, json_id_map

    def _derive_campuses_from_groups(self, group_items: list | None) -> list:
        """
        Builds a list of campus objects (deduplicated by name) from each group's
        'campus' sub-object so campuses can be restored even when the dedicated
        campuses_canonical.json export is empty.
        """
        if not isinstance(group_items, list):
            return []

        seen: set = set()
        derived: list = []
        for item in group_items:
            if not isinstance(item, dict):
                continue
            campus_obj = item.get("campus")
            if not isinstance(campus_obj, dict) or not campus_obj.get("name"):
                continue
            name = campus_obj["name"]
            if name in seen:
                continue
            seen.add(name)
            derived_campus = dict(campus_obj)
            if "organization_id" not in derived_campus:
                derived_campus["organization_id"] = item.get("organization_id")
            derived.append(derived_campus)
        return derived

    def _load_campuses_from_archives(self, export_path: Path) -> list:
        """
        When neither campuses_canonical.json nor group campus references are
        available, falls back to the newest prior canonical export ZIP that still
        carries campus data. This breaks the self-perpetuating campus leak where
        one empty export poisons every subsequent fallback run.
        """
        archives = sorted(
            export_path.glob(self._CANONICAL_ZIP_PATTERN),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for archive in archives:
            try:
                with zipfile.ZipFile(archive) as zf:
                    if "campuses_canonical.json" not in zf.namelist():
                        continue
                    items = json.loads(zf.read("campuses_canonical.json"))
                if isinstance(items, list) and items:
                    logger.info(
                        "Recovered {} campuses from prior archive {}",
                        len(items),
                        archive.name,
                    )
                    return items
            except Exception as exc:
                logger.debug("Skipping campus recovery from {}: {}", archive.name, exc)
        return []

    def _resolve_campus_id(self, item: dict, campus_by_name: dict):
        campus_obj = item.get("campus")
        if isinstance(campus_obj, dict):
            return campus_by_name.get(campus_obj.get("name"))
        return None

    def _resolve_organization_id(self, item: dict, org_by_json_id: dict):
        json_id = item.get("organization_id")
        if json_id is not None:
            return org_by_json_id.get(json_id)

        org_obj = item.get("organization")
        if isinstance(org_obj, dict):
            return org_by_json_id.get(org_obj.get("id"))
        return None

    def _first_campus_id(self):
        try:
            campuses = self.campus_ctrl.get_all()
            return campuses[0].id if campuses else None
        except Exception:
            return None

    def _first_organization_id(self):
        try:
            orgs = self.org_ctrl.get_all()
            return orgs[0].id if orgs else None
        except Exception:
            return None

    @staticmethod
    def _load_json(path: Path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("Failed to parse {}: {}", path.name, exc)
            return None
