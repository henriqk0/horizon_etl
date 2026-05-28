from eo_lib.infrastructure.database.postgres_client import PostgresClient
from libbase.infrastructure.sql_repository import GenericSqlRepository
from sqlalchemy.orm import sessionmaker

from src.tracking.entities import (
    AttributeAssertion,
    EntityChangeLog,
    EntityMatch,
    IngestionRun,
    SourceRecord,
)
from src.tracking.services import (
    AttributeAssertionService,
    EntityChangeLogService,
    EntityMatchService,
    IngestionRunService,
    SourceRecordService,
)


class TrackingServiceFactory:
    @staticmethod
    def _session():
        client = PostgresClient()
        return sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=client._engine,
            expire_on_commit=False,
        )()

    @staticmethod
    def create_ingestion_run_service() -> IngestionRunService:
        return IngestionRunService(
            GenericSqlRepository(TrackingServiceFactory._session(), IngestionRun)
        )

    @staticmethod
    def create_source_record_service() -> SourceRecordService:
        return SourceRecordService(
            GenericSqlRepository(TrackingServiceFactory._session(), SourceRecord)
        )

    @staticmethod
    def create_entity_match_service() -> EntityMatchService:
        return EntityMatchService(
            GenericSqlRepository(TrackingServiceFactory._session(), EntityMatch)
        )

    @staticmethod
    def create_attribute_assertion_service() -> AttributeAssertionService:
        return AttributeAssertionService(
            GenericSqlRepository(TrackingServiceFactory._session(), AttributeAssertion)
        )

    @staticmethod
    def create_entity_change_log_service() -> EntityChangeLogService:
        return EntityChangeLogService(
            GenericSqlRepository(TrackingServiceFactory._session(), EntityChangeLog)
        )
