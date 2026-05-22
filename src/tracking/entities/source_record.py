from eo_lib.domain.base import Base
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_entity_type",
            "source_record_id",
            "payload_hash",
            name="uq_source_records_source_identity_hash",
        ),
        Index("ix_source_records_file", "source_file"),
        Index("ix_source_records_payload_hash", "payload_hash"),
    )

    id = Column(Integer, primary_key=True)
    ingestion_run_id = Column(
        Integer,
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system = Column(String(50), nullable=False, index=True)
    source_entity_type = Column(String(100), nullable=False, index=True)
    source_record_id = Column(String(255), nullable=True)
    source_file = Column(String(500), nullable=True)
    source_path = Column(String(1000), nullable=True)
    raw_payload_json = Column(JSON, nullable=True)
    payload_hash = Column(String(255), nullable=False)
    extracted_at = Column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    ingestion_run = relationship("IngestionRun", back_populates="source_records")
    entity_matches = relationship(
        "EntityMatch",
        back_populates="source_record",
        cascade="all, delete-orphan",
    )
    attribute_assertions = relationship(
        "AttributeAssertion",
        back_populates="source_record",
        cascade="all, delete-orphan",
    )
    change_logs = relationship(
        "EntityChangeLog",
        back_populates="source_record",
        cascade="all, delete-orphan",
    )
