from typing import Any, Optional

from libbase.controllers.generic_controller import GenericController

from src.tracking.entities import SourceRecord
from src.tracking.service_factory import TrackingServiceFactory
from src.tracking.services import SourceRecordService


class SourceRecordController(GenericController[SourceRecord]):
    def __init__(self, service: Optional[SourceRecordService] = None):
        super().__init__(
            service or TrackingServiceFactory.create_source_record_service()
        )

    def create_source_record(
        self,
        *,
        ingestion_run_id: int,
        source_system: str,
        source_entity_type: str,
        payload_hash: str,
        source_record_id: Optional[str] = None,
        source_file: Optional[str] = None,
        source_path: Optional[str] = None,
        raw_payload_json: Optional[Any] = None,
    ) -> SourceRecord:
        return self._service.create_source_record(
            ingestion_run_id=ingestion_run_id,
            source_system=source_system,
            source_entity_type=source_entity_type,
            payload_hash=payload_hash,
            source_record_id=source_record_id,
            source_file=source_file,
            source_path=source_path,
            raw_payload_json=raw_payload_json,
        )
