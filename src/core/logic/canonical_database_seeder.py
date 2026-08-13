import json
from pathlib import Path

from eo_lib import OrganizationController
from loguru import logger
from research_domain import CampusController, ResearchGroupController


class CanonicalDatabaseSeeder:
    """
    Seeds SQLite database tables (horizon.db) from canonical export JSONs
    when live ingestion sources are unavailable or returned zero items.
    """

    def __init__(self):
        self.rg_ctrl = ResearchGroupController()
        self.campus_ctrl = CampusController()
        self.org_ctrl = OrganizationController()

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
        campus_by_name = self._seed_campuses_if_empty(export_path, org_by_json_id)

        default_campus_id = self._first_campus_id()

        seeded_count = 0
        for item in data:
            if not isinstance(item, dict) or not item.get("name"):
                continue

            name = item["name"]
            cnpq_url = item.get("cnpq_url") or item.get("site") or item.get("url")

            campus_id = self._resolve_campus_id(item, campus_by_name)
            if campus_id is None:
                campus_id = item.get("campus_id")
            if campus_id is None:
                campus_id = default_campus_id
            organization_id = self._resolve_organization_id(item, org_by_json_id)

            try:
                self.rg_ctrl.create_research_group(
                    name=name,
                    campus_id=campus_id,
                    organization_id=organization_id,
                    cnpq_url=cnpq_url,
                    description=item.get("description"),
                    short_name=item.get("short_name"),
                    site=item.get("site"),
                )
                seeded_count += 1
            except Exception as exc:
                logger.debug("Group seeding skipped for {}: {}", name, exc)

        logger.info(
            "Seeded {} research groups into database from {}",
            seeded_count,
            json_path.name,
        )
        return seeded_count

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
            except Exception as exc:
                logger.debug(
                    "Organization seeding skipped for {}: {}",
                    item.get("name"),
                    exc,
                )
        return mapping

    def _seed_campuses_if_empty(self, export_path: Path, org_by_json_id: dict) -> dict:
        """
        Seeds campuses from campuses_canonical.json when the campuses table is
        empty. Returns {name: db_id} mapping.
        """
        mapping: dict = {}
        try:
            if self.campus_ctrl.get_all():
                return mapping
        except Exception as exc:
            logger.debug("Failed to query existing campuses: {}", exc)
            return mapping

        items = self._load_json(export_path / "campuses_canonical.json")
        if not isinstance(items, list):
            return mapping

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
            except Exception as exc:
                logger.debug("Campus seeding skipped for {}: {}", item.get("name"), exc)

        return mapping

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
