from eo_lib.domain.base import Base
from sqlalchemy import (
    JSON,
    Boolean,
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


class AttributeAssertion(Base):
    __tablename__ = "attribute_assertions"
    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "canonical_entity_type",
            "canonical_entity_id",
            "attribute_name",
            "value_hash",
            name="uq_attribute_assertions_source_entity_attribute_value",
        ),
        Index(
            "ix_attribute_assertions_selected",
            "canonical_entity_type",
            "canonical_entity_id",
            "attribute_name",
            "is_selected",
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
    attribute_name = Column(String(255), nullable=False, index=True)
    value_json = Column(JSON, nullable=True)
    value_hash = Column(String(255), nullable=False, index=True)
    is_selected = Column(Boolean, nullable=False, default=False, index=True)
    selection_reason = Column(String(255), nullable=True)
    asserted_at = Column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    source_record = relationship("SourceRecord", back_populates="attribute_assertions")
