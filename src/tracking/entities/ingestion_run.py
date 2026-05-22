from eo_lib.domain.base import Base
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True)
    source_system = Column(String(50), nullable=False, index=True)
    flow_name = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="running", index=True)
    input_snapshot_hash = Column(String(255), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)

    source_records = relationship(
        "SourceRecord",
        back_populates="ingestion_run",
        cascade="all, delete-orphan",
    )
    change_logs = relationship(
        "EntityChangeLog",
        back_populates="ingestion_run",
        cascade="all, delete-orphan",
    )
