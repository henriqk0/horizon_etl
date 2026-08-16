from typing import Any, Dict, List, Optional, Set, Tuple

from eo_lib import TeamController
from loguru import logger

from src.core.logic.initiative_identity import normalize_text


class TeamSynchronizer:
    """
    Service responsible for team management and membership synchronization.

    This class handles identifying/creating teams and synchronizing their members
    based on the source data, ensuring that only current members are retained.
    """

    def __init__(self, team_controller: TeamController, roles_cache: Dict[str, Any]):
        """
        Initializes the TeamSynchronizer.

        Args:
            team_controller (TeamController): Controller used to interact with Team records.
            roles_cache (Dict[str, Any]): Cache of Role objects for quick lookup.
        """
        self.team_controller = team_controller
        self.roles_cache = roles_cache
        self._teams_cache = None
        self._teams_by_normalized: Dict[str, Any] = {}

    def _ensure_teams_loaded(self) -> None:
        if self._teams_cache is None:
            self._teams_cache = self.team_controller.get_all()
            self._teams_by_normalized = {}
            for t in self._teams_cache:
                t_name = (
                    t.name
                    if hasattr(t, "name")
                    else (t.get("name") if isinstance(t, dict) else "")
                )
                if not t_name:
                    continue
                key = normalize_text(t_name)
                if key and key not in self._teams_by_normalized:
                    self._teams_by_normalized[key] = t

    def ensure_team(self, team_name: str, description: str) -> Optional[Any]:
        """
        Ensures a team exists with the given name. If not, creates it.

        Args:
            team_name (str): The name of the team.
            description (str): Description for the team if creation is needed.

        Returns:
            Optional[Any]: The existing or newly created Team object, or None if error.
        """
        try:
            self._ensure_teams_loaded()
            team_name_key = normalize_text(team_name)
            if team_name_key and team_name_key in self._teams_by_normalized:
                logger.debug(f"Team already exists: {team_name[:50]}...")
                return self._teams_by_normalized[team_name_key]

            team = self.team_controller.create_team(
                name=team_name, description=description
            )
            logger.info(f"Created team: {team_name[:50]}...")
            # Add newly created team to cache so subsequent lookups don't reload
            if self._teams_cache is not None:
                self._teams_cache.append(team)
            if team_name_key:
                self._teams_by_normalized.setdefault(team_name_key, team)
            return team
        except Exception as e:
            logger.warning(f"Failed to manage team '{team_name[:50]}': {e}")
            return None

    def synchronize_members(
        self, team_id: int, members_to_sync: List[Tuple[Any, str, Optional[Any]]]
    ):
        """
        Synchronizes team members: adds new ones and removes obsolete ones.
        Loads the current member list once per team to avoid N+1 queries.
        """
        try:
            current_members = self.team_controller.get_members(team_id)
        except Exception:
            current_members = []

        current_source_memberships: Set[Tuple[int, int]] = set()

        for person, role_name, start_date in members_to_sync:
            if not person:
                continue

            role_obj = self.roles_cache.get(role_name)
            role_id = getattr(role_obj, "id", None) or (
                role_obj.get("id") if isinstance(role_obj, dict) else None
            )

            if role_id:
                current_source_memberships.add((person.id, role_id))

            # Add member with idempotency check (reuses cached member list)
            self._add_member_if_new(
                team_id,
                person,
                role_obj,
                role_name,
                role_id,
                start_date,
                current_members=current_members,
            )

        # Remove obsolete members (reuses cached member list)
        self._remove_obsolete_members(
            team_id, current_source_memberships, current_members=current_members
        )

    def add_members(
        self, team_id: int, members_to_add: List[Tuple[Any, str, Optional[Any]]]
    ):
        """
        Adds members to the team without removing existing ones.
        Idempotent: only adds if (person, role, start_date) is missing.
        Loads the current member list once to avoid N+1 queries.
        """
        try:
            current_members = self.team_controller.get_members(team_id)
        except Exception:
            current_members = []

        for person, role_name, start_date in members_to_add:
            if not person:
                continue

            role_obj = self.roles_cache.get(role_name)
            role_id = getattr(role_obj, "id", None) or (
                role_obj.get("id") if isinstance(role_obj, dict) else None
            )

            # Add member with idempotency check (reuses cached member list)
            self._add_member_if_new(
                team_id,
                person,
                role_obj,
                role_name,
                role_id,
                start_date,
                current_members=current_members,
            )

    def _add_member_if_new(
        self,
        team_id,
        person,
        role_obj,
        role_name,
        role_id,
        start_date,
        current_members=None,
    ):
        """
        Adds a member to the team if they are not already present with the same role and start date.

        Args:
            team_id (int): ID of the team.
            person (Person): Person object to add.
            role_obj (Any): Role object for the membership.
            role_name (str): Name of the role (for logging).
            role_id (int): ID of the role.
            start_date (Optional[Any]): The start date of the membership.
            current_members (Optional[list]): Pre-loaded member list to avoid DB re-query.
        """
        try:
            if current_members is None:
                current_members = self.team_controller.get_members(team_id)
            for m in current_members:
                m_person_id = getattr(m, "person_id", None)
                m_role_id = getattr(m, "role_id", None)
                m_start = getattr(m, "start_date", None)

                dates_match = True
                if m_start and start_date:
                    m_start_iso = (
                        m_start.isoformat()
                        if hasattr(m_start, "isoformat")
                        else str(m_start)
                    )
                    start_date_iso = (
                        start_date.isoformat()
                        if hasattr(start_date, "isoformat")
                        else str(start_date)
                    )
                    dates_match = m_start_iso == start_date_iso
                elif m_start or start_date:
                    dates_match = False

                if m_person_id == person.id and m_role_id == role_id and dates_match:
                    return
        except Exception as e:
            logger.warning(f"Failed to check member existence: {e}")

        try:
            self.team_controller.add_member(
                team_id=team_id,
                person_id=person.id,
                role=role_obj or role_name,
                start_date=start_date,
            )
        except Exception as e:
            logger.warning(f"Failed to add {role_name} '{person.name}': {e}")

    def _remove_obsolete_members(
        self,
        team_id: int,
        current_source_memberships: Set[Tuple[int, int]],
        current_members=None,
    ):
        """
        Removes members from the database that are not present in the current source data.

        Args:
            team_id (int): ID of the team.
            current_source_memberships (Set[Tuple[int, int]]):
                Set of (PersonID, RoleID) that should currently belong to the team.
            current_members (Optional[list]): Pre-loaded member list to avoid DB re-query.
        """
        try:
            if current_members is None:
                current_members = self.team_controller.get_members(team_id)
            for m in current_members:
                m_person_id = getattr(m, "person_id", None)
                m_role_id = getattr(m, "role_id", None)

                if (m_person_id, m_role_id) not in current_source_memberships:
                    logger.info(
                        f"Removing obsolete member (Person ID: {m_person_id}, Role ID: {m_role_id}) from team {team_id}"
                    )
                    try:
                        m_id = getattr(m, "id", None)
                        if m_id:
                            self.team_controller.remove_member(m_id)
                        else:
                            logger.warning(
                                f"Could not find member ID for obsolete membership (Person {m_person_id})"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to remove obsolete member: {e}")
        except Exception as e:
            logger.warning(f"Failed to synchronize team members: {e}")
