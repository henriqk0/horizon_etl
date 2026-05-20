
from typing import Any, Dict, Optional

from eo_lib import (
    InitiativeController,
    PersonController,
    OrganizationController
)
from eo_lib.domain import Role
from eo_lib.infrastructure.database.postgres_client import PostgresClient
from loguru import logger
from research_domain.controllers import (
    UniversityController,
    EducationTypeController,
    AcademicEducationController,
    CampusController,
    KnowledgeAreaController,
    RoleController,
    ArticleController
)

from src.core.logic.initiative_identity import normalize_text


class EntityManager:
    """
    Handles the creation and retrieval of base domain entities (Organization, Roles, Types, Campus, Knowledge Areas).
    Provides caching for frequently accessed entities like Roles.
    """

    ROLES = ["Coordinator", "Researcher", "Student", "Sponsor"]

    def __init__(
        self,
        initiative_controller: InitiativeController,
        person_controller: PersonController,
    ):
        self.initiative_controller = initiative_controller
        self.person_controller = person_controller
        self.campus_controller = CampusController()
        self.ka_controller = KnowledgeAreaController()
        self.role_controller = RoleController()
        self.uni_controller = UniversityController()
        self.edu_type_controller = EducationTypeController()
        self.academic_edu_controller = AcademicEducationController()
        self.article_controller = ArticleController()
        self.org_controller = OrganizationController()

        self._roles_cache: Dict[str, Role] = {}

    def ensure_organization(
        self, name: str = "Instituto Federal do Espírito Santo", short_name: str = None
    ) -> Optional[int]:
        """Ensure an organization exists and return its ID."""
        if not name:
            return None

        # If using the default name and short_name is not provided, default it to IFES
        if name == "Instituto Federal do Espírito Santo" and short_name is None:
            short_name = "IFES"

        try:

            target_norm = normalize_text(name)
            target_short_norm = normalize_text(short_name) if short_name else ""

            orgs = self.uni_controller.get_all()
            for o in orgs:
                o_name = o.name if hasattr(o, "name") else o.get("name", "")
                o_short_name = (
                    o.short_name
                    if hasattr(o, "short_name")
                    else o.get("short_name", "")
                )

                if normalize_text(o_name) == target_norm or (
                    target_short_norm and normalize_text(o_short_name) == target_short_norm
                ):
                    return o.id if hasattr(o, "id") else o.get("id")

            # If not found, create one
            logger.info(f"Creating Organization: {name}...")
            new_org = self.uni_controller.create_university(
                name=name, short_name=short_name
            )
            return new_org.id if hasattr(new_org, "id") else new_org.get("id")
        except Exception as e:
            logger.warning(f"Failed to ensure organization '{name}': {e}")
            return None

    def get_organization(self, org_id: int) -> Optional[Any]:
        """Retrieve organization object by ID."""
        try:
            return self.org_controller.get_by_id(org_id)
        except Exception as e:
            logger.warning(f"Failed to get organization {org_id}: {e}")
            return None

    def ensure_roles(self) -> Dict[str, Role]:
        """Ensure mandatory roles exist and return the roles cache."""
        try:
            existing_roles = self.role_controller.get_all()
            db_roles = {}
            for r in existing_roles:
                r_name = r.name if hasattr(r, "name") else r.get("name")
                if r_name:
                    db_roles[r_name] = r

            for role_name in self.ROLES:
                if role_name not in db_roles:
                    logger.info(f"Creating role: {role_name}")
                    new_role = self.role_controller.create_role(
                        name=role_name, description=f"Role: {role_name}"
                    )
                    self._roles_cache[role_name] = new_role
                else:
                    logger.debug(f"Role already exists: {role_name}")
                    self._roles_cache[role_name] = db_roles[role_name]
        except Exception as e:
            logger.warning(f"Error ensuring roles exist via controller: {e}")
            self._ensure_roles_fallback()

        return self._roles_cache

    def _ensure_roles_fallback(self) -> None:
        """Fallback to direct DB access for ensuring roles."""
        try:
            client = PostgresClient()
            session = client.get_session()
            for role_name in self.ROLES:
                existing = session.query(Role).filter_by(name=role_name).first()
                if not existing:
                    new_role = Role(name=role_name, description=f"Role: {role_name}")
                    session.add(new_role)
                    session.commit()
                    logger.info(f"Created role (fallback): {role_name}")
                    self._roles_cache[role_name] = new_role
                else:
                    self._roles_cache[role_name] = existing
        except Exception as e:
            logger.error(f"Critical failure ensuring roles in fallback: {e}")

    def ensure_initiative_type(self, type_name: str = "Research Project") -> Any:
        """Ensure the specified initiative type exists."""
        initiative_type = None
        existing_types = self.initiative_controller.list_initiative_types()

        for t in existing_types:
            t_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", "")
            if t_name == type_name:
                if isinstance(t, dict):

                    class Obj:
                        pass

                    initiative_type = Obj()
                    initiative_type.id = t.get("id")
                    initiative_type.name = t.get("name")
                else:
                    initiative_type = t
                break

        if not initiative_type:
            logger.info(f"Creating Initiative Type: {type_name}")
            try:
                new_type_result = self.initiative_controller.create_initiative_type(
                    name=type_name,
                    description=f"Iniciativas do tipo {type_name} importadas",
                )

                if isinstance(new_type_result, dict):

                    class Obj:
                        pass

                    initiative_type = Obj()
                    initiative_type.id = new_type_result.get("id")
                    initiative_type.name = new_type_result.get("name")
                else:
                    initiative_type = new_type_result

            except Exception as e:
                logger.error(f"Failed to create initiative type {type_name}: {e}")
                raise e

        return initiative_type

    def resolve_campus(self, campus_name: Optional[str], org_id: Optional[int]) -> Optional[int]:
        """Resolve a campus name to an ID, creating it if necessary."""
        if not campus_name or not isinstance(campus_name, str):
            campus_name = "Reitoria"

        try:
            campuses = self.campus_controller.get_all()

            target_norm = normalize_text(campus_name)

            for c in campuses:
                c_name = c.name if hasattr(c, "name") else c.get("name")
                c_org = (
                    c.organization_id
                    if hasattr(c, "organization_id")
                    else c.get("organization_id")
                    if isinstance(c, dict)
                    else None
                )
                if c_name and normalize_text(c_name) == target_norm and (
                    org_id is None or c_org is None or c_org == org_id
                ):
                    return c.id if hasattr(c, "id") else c.get("id")

            if org_id and len(campus_name) > 3:
                logger.info(f"Creating missing Campus: {campus_name}")
                new_campus = self.campus_controller.create_campus(
                    name=campus_name, organization_id=org_id
                )
                return (
                    new_campus.id if hasattr(new_campus, "id") else new_campus.get("id")
                )

        except Exception as e:
            logger.warning(f"Error resolving campus '{campus_name}': {e}")

        return None

    def ensure_knowledge_area(self, name: str) -> Optional[int]:
        """Ensure Knowledge Area exists and return its ID."""
        if not name:
            return None

        try:
            norm_name = normalize_text(name)
        except Exception:
            return None

        try:
            all_kas = self.ka_controller.get_all()
            for ka in all_kas:
                k_name = ka.name if hasattr(ka, "name") else ka.get("name")
                if k_name:
                    try:
                        k_norm = normalize_text(k_name)
                        if k_norm == norm_name:
                            return ka.id if hasattr(ka, "id") else ka.get("id")
                    except Exception:
                        continue

            logger.info(f"Creating Knowledge Area: {name}")
            new_ka = self.ka_controller.create_knowledge_area(name=name)
            return new_ka.id if hasattr(new_ka, "id") else new_ka.get("id")

        except Exception as e:
            logger.warning(f"Failed to ensure Knowledge Area '{name}': {e}")
            return None

    def ensure_education_type(self, name: str) -> Optional[int]:
        """Ensure Education Type exists and return its ID."""
        if not name:
            return None

        try:
            # Check existing
            all_types = self.edu_type_controller.get_all()
            for t in all_types:
                t_name = t.name if hasattr(t, "name") else t.get("name")
                if normalize_text(t_name) == normalize_text(name):
                    return t.id if hasattr(t, "id") else t.get("id")

            # Create
            logger.info(f"Creating Education Type: {name}")
            new_type = self.edu_type_controller.create_education_type(name=name)

            # The controller returns the object or a dict depending on implementation
            # In v0.12.7 it returns the object directly
            return new_type.id if hasattr(new_type, "id") else new_type.get("id")
        except Exception as e:
            logger.error(f"Failed to ensure Education Type '{name}': {e}")
            return None
