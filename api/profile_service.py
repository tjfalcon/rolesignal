import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from api.database import create_database_engine, create_session_factory, database_url, session_scope
from api.db_models import CandidateProfileRecord, EvidenceRecord, ResumeVersionRecord
from api.models import (
    CandidateProfileDetail,
    EvidenceCreate,
    EvidenceUpdate,
    ManagedEvidence,
    ResumeVersionCreate,
    ResumeVersionDetail,
    ResumeVersionSummary,
)
from api.retrieval import local_embedding


class ProfileStoreUnavailableError(RuntimeError):
    pass


class ProfileNotFoundError(LookupError):
    pass


class VersionNotFoundError(LookupError):
    pass


class ActiveVersionMutationError(RuntimeError):
    pass


class InvalidActivationError(RuntimeError):
    pass


class ProfileService:
    def __init__(self, engine: Engine, factory: sessionmaker[Session] | None = None) -> None:
        self.engine = engine
        self.factory = factory or create_session_factory(engine)

    def get_profile(self, profile_id: str) -> CandidateProfileDetail:
        with session_scope(self.factory) as session:
            profile = session.get(CandidateProfileRecord, profile_id)
            if profile is None:
                raise ProfileNotFoundError(profile_id)
            versions = session.scalars(
                select(ResumeVersionRecord)
                .where(ResumeVersionRecord.profile_id == profile_id)
                .order_by(ResumeVersionRecord.version_number.desc())
            ).all()
            counts: dict[str | None, int] = {
                version_id: count
                for version_id, count in session.execute(
                    select(EvidenceRecord.resume_version_id, func.count())
                    .where(EvidenceRecord.profile_id == profile_id)
                    .group_by(EvidenceRecord.resume_version_id)
                ).all()
            }
            return CandidateProfileDetail(
                id=profile.id,
                display_name=profile.display_name,
                headline=profile.headline,
                visibility=profile.visibility,
                active_resume_version_id=profile.active_resume_version_id,
                versions=[
                    self._version_summary(version, counts.get(version.id, 0))
                    for version in versions
                ],
            )

    def get_version(self, version_id: str) -> ResumeVersionDetail:
        with session_scope(self.factory) as session:
            version = self._require_version(session, version_id)
            evidence = session.scalars(
                select(EvidenceRecord)
                .where(EvidenceRecord.resume_version_id == version_id)
                .order_by(EvidenceRecord.created_at, EvidenceRecord.id)
            ).all()
            return ResumeVersionDetail(
                **self._version_summary(version, len(evidence)).model_dump(),
                profile_id=version.profile_id,
                evidence=[self._managed_evidence(item) for item in evidence],
            )

    def create_version(self, profile_id: str, payload: ResumeVersionCreate) -> ResumeVersionDetail:
        with self.factory.begin() as session:
            profile = session.scalar(
                select(CandidateProfileRecord)
                .where(CandidateProfileRecord.id == profile_id)
                .with_for_update()
            )
            if profile is None:
                raise ProfileNotFoundError(profile_id)
            highest = session.scalar(
                select(func.max(ResumeVersionRecord.version_number)).where(
                    ResumeVersionRecord.profile_id == profile_id
                )
            )
            version = ResumeVersionRecord(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                version_number=(highest or 0) + 1,
                label=payload.label.strip(),
                source_name=payload.source_name.strip(),
                status="draft",
            )
            session.add(version)
            session.flush()
            if payload.copy_active_evidence and profile.active_resume_version_id:
                active_evidence = session.scalars(
                    select(EvidenceRecord).where(
                        EvidenceRecord.resume_version_id == profile.active_resume_version_id
                    )
                ).all()
                for item in active_evidence:
                    session.add(
                        EvidenceRecord(
                            id=str(uuid.uuid4()),
                            profile_id=profile_id,
                            resume_version_id=version.id,
                            claim=item.claim,
                            skill_tags=item.skill_tags,
                            skill_text=item.skill_text,
                            source=item.source,
                            source_locator=item.source_locator,
                            visibility=item.visibility,
                            approved=item.approved,
                            embedding=item.embedding,
                        )
                    )
        return self.get_version(version.id)

    def add_evidence(self, version_id: str, payload: EvidenceCreate) -> ManagedEvidence:
        with self.factory.begin() as session:
            version = self._require_draft(session, version_id)
            skill_tags = self._normalize_tags(payload.skill_tags)
            claim = payload.claim.strip()
            evidence = EvidenceRecord(
                id=str(uuid.uuid4()),
                profile_id=version.profile_id,
                resume_version_id=version.id,
                claim=claim,
                skill_tags=skill_tags,
                skill_text=" ".join(skill_tags),
                source=payload.source.strip(),
                source_locator=payload.source_locator.strip(),
                visibility=payload.visibility,
                approved=True,
                embedding=local_embedding(f"{claim} {' '.join(skill_tags)}"),
            )
            session.add(evidence)
            session.flush()
            result = self._managed_evidence(evidence)
        return result

    def update_evidence(
        self, version_id: str, evidence_id: str, payload: EvidenceUpdate
    ) -> ManagedEvidence:
        with self.factory.begin() as session:
            self._require_draft(session, version_id)
            evidence = session.scalar(
                select(EvidenceRecord).where(
                    EvidenceRecord.id == evidence_id,
                    EvidenceRecord.resume_version_id == version_id,
                )
            )
            if evidence is None:
                raise VersionNotFoundError(evidence_id)
            changes = payload.model_dump(exclude_unset=True)
            for field in ("claim", "source", "source_locator"):
                if field in changes:
                    changes[field] = changes[field].strip()
            if "skill_tags" in changes:
                changes["skill_tags"] = self._normalize_tags(changes["skill_tags"])
                changes["skill_text"] = " ".join(changes["skill_tags"])
            for key, value in changes.items():
                setattr(evidence, key, value)
            if "claim" in changes or "skill_tags" in changes:
                evidence.embedding = local_embedding(
                    f"{evidence.claim} {' '.join(evidence.skill_tags)}"
                )
            session.flush()
            result = self._managed_evidence(evidence)
        return result

    def activate(self, version_id: str) -> CandidateProfileDetail:
        with self.factory.begin() as session:
            version = self._require_version(session, version_id, for_update=True)
            if version.status != "draft":
                raise ActiveVersionMutationError("Only a draft version can be activated")
            approved_count = session.scalar(
                select(func.count())
                .select_from(EvidenceRecord)
                .where(
                    EvidenceRecord.resume_version_id == version_id,
                    EvidenceRecord.approved.is_(True),
                    EvidenceRecord.visibility == "public",
                )
            )
            if not approved_count:
                raise InvalidActivationError(
                    "A version needs at least one approved public evidence item"
                )
            profile = session.scalar(
                select(CandidateProfileRecord)
                .where(CandidateProfileRecord.id == version.profile_id)
                .with_for_update()
            )
            if profile is None:
                raise ProfileNotFoundError(version.profile_id)
            if profile.active_resume_version_id:
                previous = session.get(ResumeVersionRecord, profile.active_resume_version_id)
                if previous is not None:
                    previous.status = "archived"
                    # Satisfy the partial unique index before promoting the draft.
                    session.flush()
            version.status = "active"
            version.activated_at = datetime.now(UTC)
            profile.active_resume_version_id = version.id
        return self.get_profile(version.profile_id)

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()))
        if not normalized:
            raise ValueError("At least one non-empty skill tag is required")
        return normalized

    @staticmethod
    def _require_version(
        session: Session, version_id: str, *, for_update: bool = False
    ) -> ResumeVersionRecord:
        statement = select(ResumeVersionRecord).where(ResumeVersionRecord.id == version_id)
        if for_update:
            statement = statement.with_for_update()
        version = session.scalar(statement)
        if version is None:
            raise VersionNotFoundError(version_id)
        return version

    def _require_draft(self, session: Session, version_id: str) -> ResumeVersionRecord:
        version = self._require_version(session, version_id, for_update=True)
        if version.status != "draft":
            raise ActiveVersionMutationError("Active and archived versions are immutable")
        return version

    @staticmethod
    def _version_summary(version: ResumeVersionRecord, count: int) -> ResumeVersionSummary:
        return ResumeVersionSummary(
            id=version.id,
            version_number=version.version_number,
            label=version.label,
            status=version.status,
            source_name=version.source_name,
            evidence_count=count,
            created_at=version.created_at,
            activated_at=version.activated_at,
        )

    @staticmethod
    def _managed_evidence(record: EvidenceRecord) -> ManagedEvidence:
        return ManagedEvidence(
            id=record.id,
            claim=record.claim,
            skill_tags=record.skill_tags,
            source=record.source,
            source_locator=record.source_locator,
            visibility=record.visibility,
            approved=record.approved,
        )


def create_profile_service() -> ProfileService | None:
    url = database_url()
    return ProfileService(create_database_engine(url)) if url else None


def require_profile_service(service: ProfileService | None) -> ProfileService:
    if service is None:
        raise ProfileStoreUnavailableError("PostgreSQL is required for profile management")
    return service
