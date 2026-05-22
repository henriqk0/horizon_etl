from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

# Try to import from the library
try:
    from research_domain import Researcher, ResearchGroup
except ImportError:
    # Fallback if lib is missing
    logger.warning(
        "research_domain not found. Using Mock entities for Researcher/ResearchGroup."
    )
    import uuid

    from pydantic import BaseModel, Field

    class Entity(BaseModel):
        id: uuid.UUID = Field(default_factory=uuid.uuid4)

    class ResearchGroup(Entity):
        name: str
        leader: str
        area: str
        certified: bool
        metadata: Dict[str, Any] = {}

    class Researcher(Entity):
        name: str
        role: str
        metadata: Dict[str, Any] = {}


# Project might not be in the lib yet, verify/define locally
try:
    from research_domain import Project
except ImportError:
    # logger.warning("Project entity not found in research_domain. Using local definition.")
    import uuid

    from pydantic import BaseModel, Field

    # Base Entity if not imported above
    if "Entity" not in locals():

        class Entity(BaseModel):
            id: uuid.UUID = Field(default_factory=uuid.uuid4)

    class Project(Entity):
        title: str
        status: str
        start_date: Optional[datetime] = None
        end_date: Optional[datetime] = None
        origin_id: str
        metadata: Dict[str, Any] = {}


class SigPesqMapper:
    """
    Transforms Raw Data (Dict/JSON) from SigPesq into Domain Entities.
    """

    @staticmethod
    def map_project(raw_data: Dict[str, Any]) -> Project:
        """
        Maps a raw dictionary from SigPesq to a Project entity.
        """
        try:
            # Logic to parse dates, clean strings, etc.
            # Assuming raw_data comes with keys like 'titulo', 'situacao', etc.
            title = raw_data.get("titulo", "Untitled").strip()
            status = raw_data.get("situacao", "Unknown").strip()
            origin_id = str(raw_data.get("id_projeto", ""))

            # Date parsing logic (simplified for example)
            start_date = None
            if "data_inicio" in raw_data:
                try:
                    start_date = datetime.strptime(raw_data["data_inicio"], "%d/%m/%Y")
                except ValueError:
                    pass

            return Project(
                title=title,
                status=status,
                start_date=start_date,
                origin_id=origin_id,
                metadata={"original_source": "sigpesq", "raw": raw_data},
            )
        except Exception as e:
            logger.error(f"Error mapping project: {e}")
            raise e

    @staticmethod
    def map_research_group(raw_data: Dict[str, Any]) -> ResearchGroup:
        try:
            name = raw_data.get("nome_grupo", "Unnamed Group").strip()
            leader = raw_data.get("lider", "Unknown").strip()  # noqa: F841
            area = raw_data.get("area", "General").strip()  # noqa: F841
            certified = bool(raw_data.get("certificado", False))  # noqa: F841

            return ResearchGroup(
                name=name,
                # metadata mapping removed as it is not supported in v0.4.0 entities
                # keeping variables for checking if needed later: leader, area, certified
            )
        except Exception as e:
            logger.error(f"Error mapping research group: {e}")
            raise e

    @staticmethod
    def map_researcher(raw_data: Dict[str, Any]) -> Researcher:
        try:
            name = raw_data.get("nome", "Unknown").strip()
            role = raw_data.get(  # noqa: F841
                "funcao", "Researcher"
            ).strip()  # e.g. Bolsista, Coordenador

            return Researcher(
                name=name,
                # metadata mapping removed as it is not supported in v0.4.0 entities
                # keeping variables for checking if needed later: role
            )
        except Exception as e:
            logger.error(f"Error mapping researcher: {e}")
            raise e
