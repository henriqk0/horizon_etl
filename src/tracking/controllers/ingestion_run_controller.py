from datetime import datetime
from typing import Optional

from libbase.controllers.generic_controller import GenericController

from src.tracking.entities import IngestionRun
from src.tracking.service_factory import TrackingServiceFactory
from src.tracking.services import IngestionRunService


class IngestionRunController(GenericController[IngestionRun]):
    def __init__(self, service: Optional[IngestionRunService] = None):
        super().__init__(
            service or TrackingServiceFactory.create_ingestion_run_service()
        )

    def create_run(
        self,
        *,
        source_system: str,
        flow_name: str,
        status: str = "running",
        input_snapshot_hash: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> IngestionRun:
        return self._service.create_run(
            source_system=source_system,
            flow_name=flow_name,
            status=status,
            input_snapshot_hash=input_snapshot_hash,
            notes=notes,
        )

    def finalize_run(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> IngestionRun:
        return self._service.finalize_run(
            run_id,
            status=status,
            finished_at=finished_at,
            notes=notes,
        )
