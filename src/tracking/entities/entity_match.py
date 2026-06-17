from eo_lib.domain.base import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class EntityMatch(Base):
    __tablename__ = "entity_matches"
    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "canonical_entity_type",
            "canonical_entity_id",
            name="uq_entity_matches_source_record_canonical_target",
        ),
        Index(
            "ix_entity_matches_canonical_target",
            "canonical_entity_type",
            "canonical_entity_id",
        ),
    )

    id = Column(Integer, primary_key=True)
    source_record_id = Column(
        Integer,
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canonical_entity_type = Column(String(100), nullable=False, index=True)
    canonical_entity_id = Column(Integer, nullable=False, index=True)
    match_strategy = Column(String(100), nullable=False, index=True)
    match_confidence = Column(Numeric(5, 2), nullable=True)
    matched_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    source_record = relationship("SourceRecord", back_populates="entity_matches")
