from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional, Tuple


class OrganizationStrategy(ABC):
    @abstractmethod
    def ensure(self, uni_ctrl) -> int:
        pass


class CampusStrategy(ABC):
    @abstractmethod
    def ensure(self, campus_ctrl, campus_name: str, org_id: int) -> int:
        pass


class KnowledgeAreaStrategy(ABC):
    @abstractmethod
    def ensure(self, area_ctrl, area_name: str) -> Optional[int]:
        pass


class ResearcherStrategy(ABC):
    @abstractmethod
    def ensure(self, researcher_ctrl, name: str, email: str = None):
        pass


class RoleStrategy(ABC):
    @abstractmethod
    def ensure_leader(self, role_ctrl):
        pass


class ResearchGroupMappingStrategy(ABC):
    """Base interface for Research Group mapping strategies."""

    @abstractmethod
    def map_row(self, row: dict) -> dict:
        """
        Maps a raw row from the source into a standardized format.
        Expected keys in returned dict:
            - name (str)
            - short_name (str)
            - campus_name (str)
            - area_name (str)
            - site_url (str)
            - leaders_raw (str)
        """
        pass

    @abstractmethod
    def parse_leaders(self, leaders_str: str) -> List[Tuple[str, Optional[str]]]:
        """
        Parses a string of leaders into a list of (name, email) tuples.
        """
        pass


class ProjectMappingStrategy(ABC):
    """Base interface for Project mapping strategies."""

    @abstractmethod
    def map_row(self, row: dict) -> dict:
        """
        Maps a raw row from the source into a standardized format.
        Expected keys in returned dict:
            - title (str)
            - status (str)
            - start_date (datetime | str)
            - end_date (datetime | str)
            - description (str, optional)
            - metadata (dict, optional)
        """
        pass

    def _parse_names(self, names_str: Any) -> List[str]:
        """Separates names by semicolon and cleans whitespace."""
        import pandas as pd

        if not names_str or pd.isna(names_str):
            return []
        return [name.strip() for name in str(names_str).split(";") if name.strip()]

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """Parses a date from various string formats or datetime objects."""
        from datetime import datetime

        import pandas as pd

        if pd.isna(date_val) or not date_val:
            return None

        if isinstance(date_val, datetime):
            return date_val

        str_val = str(date_val).strip()
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]

        for fmt in formats:
            try:
                return datetime.strptime(str_val, fmt)
            except ValueError:
                continue

        from loguru import logger

        logger.warning(f"Could not parse date: {str_val}")
        return None

    @staticmethod
    def parse_currency(value_str: Any) -> float:
        """Converts Portuguese currency strings to float.

        Handles formats:
          "1.500,00" -> 1500.0  (Brazilian thousand/decimal separators)
          "R$ 400,00" -> 400.0  (with currency prefix)
          "400,00"    -> 400.0  (comma as decimal)
          400.0       -> 400.0  (raw numeric)
        """
        if value_str is None:
            return 0.0
        if isinstance(value_str, (int, float)):
            return float(value_str)
        if hasattr(value_str, "isna") and value_str.isna():
            return 0.0
        s = str(value_str).strip().replace("R$", "").strip()
        if not s:
            return 0.0
        try:
            if "," in s and "." in s:
                if s.rfind(",") > s.rfind("."):
                    s = s.replace(".", "").replace(",", ".")
                else:
                    s = s.replace(",", "")
            elif "," in s:
                s = s.replace(",", ".")
            return float(s)
        except (ValueError, TypeError):
            return 0.0
