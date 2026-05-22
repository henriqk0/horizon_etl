from datetime import date, datetime

import pytest
from eo_lib.domain.base import Base
from libbase.infrastructure.sql_repository import GenericSqlRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tracking.context import current_ingestion_run_id
from src.tracking.controllers import (
    AttributeAssertionController,
    EntityChangeLogController,
    EntityMatchController,
    IngestionRunController,
    SourceRecordController,
)
from src.tracking.entities import (
    AttributeAssertion,
    EntityChangeLog,
    EntityMatch,
    IngestionRun,
    SourceRecord,
)
from src.tracking.recorder import TrackingRecorder
from src.tracking.services import (
    AttributeAssertionService,
    EntityChangeLogService,
    EntityMatchService,
    IngestionRunService,
    SourceRecordService,
)


def test_tracking_domain_entities_persist_end_to_end():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    run_service = IngestionRunService(GenericSqlRepository(session, IngestionRun))
    source_service = SourceRecordService(GenericSqlRepository(session, SourceRecord))
    match_service = EntityMatchService(GenericSqlRepository(session, EntityMatch))
    assertion_service = AttributeAssertionService(
        GenericSqlRepository(session, AttributeAssertion)
    )
    change_log_service = EntityChangeLogService(
        GenericSqlRepository(session, EntityChangeLog)
    )

    run = run_service.create_run(source_system="lattes", flow_name="ingest_lattes")
    record = source_service.create_source_record(
        ingestion_run_id=run.id,
        source_system="lattes",
        source_entity_type="researcher",
        source_record_id="8400407353673370",
        source_file="00_Paulo.json",
        source_path="data/lattes_json/00_Paulo.json",
        raw_payload_json={"nome": "Paulo"},
        payload_hash="hash-1",
    )
    entity_match = match_service.create_match(
        source_record_id=record.id,
        canonical_entity_type="researcher",
        canonical_entity_id=2981,
        match_strategy="lattes_id_exact",
        match_confidence=1.0,
    )
    assertion = assertion_service.create_assertion(
        source_record_id=record.id,
        canonical_entity_type="researcher",
        canonical_entity_id=2981,
        attribute_name="resume",
        value_hash="hash-resume",
        value_json={"resume": "texto"},
        is_selected=True,
        selection_reason="lattes_preferred",
    )
    change_log = change_log_service.create_change_log(
        ingestion_run_id=run.id,
        source_record_id=record.id,
        canonical_entity_type="researcher",
        canonical_entity_id=2981,
        operation="update",
        changed_fields_json=["resume"],
        before_json={"resume": None},
        after_json={"resume": "texto"},
        reason="Updated from Lattes",
    )
    finalized = run_service.finalize_run(run.id, status="success")

    assert run.id is not None
    assert record.id is not None
    assert entity_match.id is not None
    assert assertion.id is not None
    assert change_log.id is not None
    assert finalized.status == "success"
    assert finalized.finished_at is not None


def _build_tracking_recorder(session):
    recorder = TrackingRecorder.__new__(TrackingRecorder)
    recorder.ingestion_run_ctrl = IngestionRunController(
        IngestionRunService(GenericSqlRepository(session, IngestionRun))
    )
    recorder.source_record_ctrl = SourceRecordController(
        SourceRecordService(GenericSqlRepository(session, SourceRecord))
    )
    recorder.entity_match_ctrl = EntityMatchController(
        EntityMatchService(GenericSqlRepository(session, EntityMatch))
    )
    recorder.attribute_assertion_ctrl = AttributeAssertionController(
        AttributeAssertionService(GenericSqlRepository(session, AttributeAssertion))
    )
    recorder.entity_change_log_ctrl = EntityChangeLogController(
        EntityChangeLogService(GenericSqlRepository(session, EntityChangeLog))
    )
    return recorder


def test_tracking_recorder_serializes_temporal_json_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    recorder = _build_tracking_recorder(session)

    observed_at = datetime(2026, 3, 29, 12, 34, 56)
    ended_on = date(2026, 3, 29)

    with recorder.run_context(source_system="sigpesq", flow_name="sync_groups"):
        source_record = recorder.record_source_record(
            source_entity_type="research_group",
            payload={"observed_at": observed_at},
            source_record_id="group-1",
        )
        recorder.record_attribute_assertions(
            source_record_id=source_record.id,
            canonical_entity_type="research_group",
            canonical_entity_id=1,
            selected_attributes={"end_date": ended_on},
            selection_reason="normalized date",
        )
        recorder.record_change(
            source_record_id=source_record.id,
            canonical_entity_type="research_group",
            canonical_entity_id=1,
            operation="update",
            changed_fields=["observed_at", "end_date"],
            before={
                "observed_at": observed_at,
                "end_date": datetime(2026, 3, 29, 0, 0),
            },
            after={"observed_at": observed_at, "end_date": ended_on},
            reason="Normalize temporal fields",
        )

    persisted_record = session.query(SourceRecord).one()
    persisted_assertion = session.query(AttributeAssertion).one()
    persisted_change = session.query(EntityChangeLog).one()
    persisted_run = session.query(IngestionRun).one()

    assert persisted_record.raw_payload_json == {"observed_at": "2026-03-29T12:34:56"}
    assert persisted_assertion.value_json == "2026-03-29"
    assert persisted_change.before_json == {
        "observed_at": "2026-03-29T12:34:56",
        "end_date": "2026-03-29T00:00:00",
    }
    assert persisted_change.after_json == {
        "observed_at": "2026-03-29T12:34:56",
        "end_date": "2026-03-29",
    }
    assert persisted_run.status == "success"


def test_tracking_recorder_finalizes_failed_run_after_session_error():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    recorder = _build_tracking_recorder(session)

    with pytest.raises(Exception, match="not JSON serializable"):
        with recorder.run_context(source_system="sigpesq", flow_name="sync_groups"):
            recorder.entity_change_log_ctrl.create_change_log(
                ingestion_run_id=current_ingestion_run_id.get(),
                canonical_entity_type="research_group",
                canonical_entity_id=1,
                operation="update",
                before_json={"end_date": datetime(2026, 3, 29, 0, 0)},
            )

    persisted_run = session.query(IngestionRun).one()
    assert persisted_run.status == "failed"
    assert "not JSON serializable" in persisted_run.notes
