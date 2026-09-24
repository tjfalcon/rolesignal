from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 192


class Base(DeclarativeBase):
    pass


class EvidenceRecord(Base):
    __tablename__ = "candidate_evidence"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    skill_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    skill_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="public")
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("ix_candidate_evidence_profile", EvidenceRecord.profile_id)
