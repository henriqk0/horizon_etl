from decimal import Decimal
from typing import Optional

from libbase.services.generic_service import GenericService

from src.tracking.entities import EntityMatch


class EntityMatchService(GenericService[EntityMatch]):
    def create_match(
        self,
        *,
        source_record_id: int,
        canonical_entity_type: str,
        canonical_entity_id: int,
        match_strategy: str,
        match_confidence: Optional[float] = None,
    ) -> EntityMatch:
        entity_match = EntityMatch(
            source_record_id=source_record_id,
            canonical_entity_type=canonical_entity_type,
            canonical_entity_id=canonical_entity_id,
            match_strategy=match_strategy,
            match_confidence=(
                Decimal(str(match_confidence)) if match_confidence is not None else None
            ),
        )
        self.create(entity_match)
        return entity_match
