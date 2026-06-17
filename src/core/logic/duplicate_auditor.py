import sqlite3
from dataclasses import dataclass
from typing import Iterable

from src.core.logic.initiative_identity import normalize_text


@dataclass
class AuditCheck:
    name: str
    sql: str
    canonicalize_first_column: bool = False


DEFAULT_CHECKS = [
    AuditCheck(
        name="persons_by_canonical_name",
        sql="SELECT id, name, identification_id FROM persons",
        canonicalize_first_column=False,
    ),
    AuditCheck(
        name="person_emails_by_lower_email",
        sql="SELECT email, COUNT(*) AS count FROM person_emails GROUP BY lower(email) HAVING count > 1",
    ),
    AuditCheck(
        name="organizations_by_name",
        sql="SELECT name, COUNT(*) AS count FROM organizations GROUP BY name HAVING count > 1",
    ),
    AuditCheck(
        name="organizational_units_by_name_org",
        sql="SELECT name, organization_id, COUNT(*) AS count FROM organizational_units GROUP BY name, organization_id HAVING count > 1",
    ),
    AuditCheck(
        name="roles_by_name",
        sql="SELECT name, COUNT(*) AS count FROM roles GROUP BY name HAVING count > 1",
    ),
    AuditCheck(
        name="initiative_types_by_name",
        sql="SELECT name, COUNT(*) AS count FROM initiative_types GROUP BY name HAVING count > 1",
    ),
    AuditCheck(
        name="teams_by_canonical_name",
        sql="SELECT id, name FROM teams",
    ),
    AuditCheck(
        name="knowledge_areas_by_canonical_name",
        sql="SELECT id, name FROM knowledge_areas",
    ),
]


class DuplicateAuditor:
    def __init__(self, db_path: str = "db/horizon.db"):
        self.db_path = db_path

    def run(self) -> dict[str, list]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            results = {
                "persons_by_canonical_name": self._canonical_duplicates(
                    conn.execute(
                        "SELECT id, name, identification_id FROM persons"
                    ).fetchall()
                ),
                "teams_by_canonical_name": self._canonical_duplicates(
                    conn.execute("SELECT id, name FROM teams").fetchall()
                ),
                "knowledge_areas_by_canonical_name": self._canonical_duplicates(
                    conn.execute("SELECT id, name FROM knowledge_areas").fetchall()
                ),
                "person_emails_by_lower_email": conn.execute(
                    "SELECT lower(email) AS email_key, COUNT(*) AS count FROM person_emails GROUP BY lower(email) HAVING count > 1"
                ).fetchall(),
                "organizations_by_name": conn.execute(
                    "SELECT name, COUNT(*) AS count FROM organizations GROUP BY name HAVING count > 1"
                ).fetchall(),
                "organizational_units_by_name_org": conn.execute(
                    "SELECT name, organization_id, COUNT(*) AS count FROM organizational_units GROUP BY name, organization_id HAVING count > 1"
                ).fetchall(),
                "roles_by_name": conn.execute(
                    "SELECT name, COUNT(*) AS count FROM roles GROUP BY name HAVING count > 1"
                ).fetchall(),
                "initiative_types_by_name": conn.execute(
                    "SELECT name, COUNT(*) AS count FROM initiative_types GROUP BY name HAVING count > 1"
                ).fetchall(),
            }
        return results

    def _canonical_duplicates(self, rows: Iterable[sqlite3.Row]) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for row in rows:
            row_dict = dict(row)
            canonical = normalize_text(row_dict.get("name"))
            if canonical:
                groups.setdefault(canonical, []).append(row_dict)

        duplicates = []
        for canonical, members in groups.items():
            if len(members) > 1:
                duplicates.append({"canonical": canonical, "members": members})
        return duplicates
