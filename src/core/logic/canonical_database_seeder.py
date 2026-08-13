import json
from pathlib import Path

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

    def seed_research_groups_if_empty(self, export_dir: str = "data/exports") -> int:
        """
        If research_groups table in horizon.db has 0 groups with cnpq_url,
        parses research_groups_canonical.json from export_dir and populates DB.
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

        json_path = Path(export_dir).resolve() / "research_groups_canonical.json"
        if not json_path.is_file():
            logger.info(
                "Canonical file {} not found; skipping DB seed.", json_path.name
            )
            return 0

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse {}: {}", json_path.name, exc)
            return 0

        if not isinstance(data, list) or not data:
            return 0

        default_campus_id = None
        try:
            campuses = self.campus_ctrl.get_all()
            if campuses:
                default_campus_id = campuses[0].id
        except Exception:
            pass

        seeded_count = 0
        for item in data:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            cnpq_url = item.get("cnpq_url") or item.get("site") or item.get("url")
            campus_id = item.get("campus_id") or default_campus_id

            if name:
                try:
                    self.rg_ctrl.create_research_group(
                        name=name,
                        campus_id=campus_id,
                        cnpq_url=cnpq_url,
                        description=item.get("description"),
                        short_name=item.get("short_name"),
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
