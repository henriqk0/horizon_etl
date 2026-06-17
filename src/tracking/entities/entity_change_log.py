from eo_lib.domain.base import Base
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class EntityChangeLog(Base):
    __tablename__ = "entity_change_logs"
    __table_args__ = (
        Index(
            "ix_entity_change_logs_target",
            "canonical_entity_type",
            "canonical_entity_id",
            "changed_at",
        ),
    )

    id = Column(Integer, primary_key=True)
    ingestion_run_id = Column(
        Integer,
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_record_id = Column(
        Integer,
        ForeignKey("source_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    canonical_entity_type = Column(String(100), nullable=False, index=True)
    canonical_entity_id = Column(Integer, nullable=False, index=True)
    operation = Column(String(50), nullable=False, index=True)
    changed_fields_json = Column(JSON, nullable=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    ingestion_run = relationship("IngestionRun", back_populates="change_logs")
    source_record = relationship("SourceRecord", back_populates="change_logs")
