from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 192


class Base(DeclarativeBase):
    pass


class CandidateProfileRecord(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')", name="ck_candidate_profiles_visibility"
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    active_resume_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ResumeVersionRecord(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("profile_id", "version_number", name="uq_resume_versions_profile_number"),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_resume_versions_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Manual entry")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    resume_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=True
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("ix_candidate_evidence_profile", EvidenceRecord.profile_id)
Index("ix_candidate_evidence_resume_version", EvidenceRecord.resume_version_id)
Index("ix_resume_versions_profile", ResumeVersionRecord.profile_id)
Index(
    "uq_resume_versions_active_profile",
    ResumeVersionRecord.profile_id,
    unique=True,
    postgresql_where=text("status = 'active'"),
)
