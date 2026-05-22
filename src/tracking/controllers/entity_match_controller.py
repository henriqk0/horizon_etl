from typing import Optional

from libbase.controllers.generic_controller import GenericController

from src.tracking.entities import EntityMatch
from src.tracking.service_factory import TrackingServiceFactory
from src.tracking.services import EntityMatchService


class EntityMatchController(GenericController[EntityMatch]):
    def __init__(self, service: Optional[EntityMatchService] = None):
        super().__init__(
            service or TrackingServiceFactory.create_entity_match_service()
        )

    def create_match(
        self,
        *,
        source_record_id: int,
        canonical_entity_type: str,
        canonical_entity_id: int,
        match_strategy: str,
        match_confidence: Optional[float] = None,
    ) -> EntityMatch:
        return self._service.create_match(
            source_record_id=source_record_id,
            canonical_entity_type=canonical_entity_type,
            canonical_entity_id=canonical_entity_id,
            match_strategy=match_strategy,
            match_confidence=match_confidence,
        )
