import os

import pytest
from sqlalchemy import func, select

from api.analyzer import analyze_job
from api.database import create_database_engine, create_session_factory, session_scope
from api.db_models import CandidateProfileRecord, ResumeVersionRecord
from api.models import EvidenceCreate, EvidenceUpdate, ResumeVersionCreate
from api.profile_service import ActiveVersionMutationError, ProfileService
from api.retrieval import RankedEvidence
from api.retrieval_backends import (
    FallbackRetrievalBackend,
    LocalRetrievalBackend,
    PostgresRetrievalBackend,
)

DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is not configured")


def services() -> tuple[ProfileService, PostgresRetrievalBackend]:
    assert DATABASE_URL is not None
    engine = create_database_engine(DATABASE_URL)
    return ProfileService(engine), PostgresRetrievalBackend(engine)


def test_create_edit_activate_version_changes_active_retrieval() -> None:
    profiles, retrieval = services()
    before = profiles.get_profile("demo-thomas")
    baseline_count = len(retrieval.load_corpus("demo-thomas"))

    factory = create_session_factory(profiles.engine)
    draft = profiles.create_version(
        "demo-thomas",
        ResumeVersionCreate(label="Applied AI draft", copy_active_evidence=True),
    )
    try:
        assert draft.status == "draft"
        assert draft.evidence_count == baseline_count

        added = profiles.add_evidence(
            draft.id,
            EvidenceCreate(
                claim=(
                    "Built RoleSignal with versioned PostgreSQL evidence and controlled activation."
                ),
                skill_tags=["PostgreSQL", "Python", "FastAPI"],
                source="RoleSignal public repository",
                source_locator="Profile versioning case study",
            ),
        )
        updated = profiles.update_evidence(
            draft.id,
            added.id,
            EvidenceUpdate(source_locator="Profile versioning implementation"),
        )
        assert updated.skill_tags == ["postgresql", "python", "fastapi"]

        activated = profiles.activate(draft.id)
        assert activated.active_resume_version_id == draft.id
        assert activated.active_resume_version_id != before.active_resume_version_id
        assert len(retrieval.load_corpus("demo-thomas")) == baseline_count + 1

        with pytest.raises(ActiveVersionMutationError):
            profiles.update_evidence(
                draft.id,
                added.id,
                EvidenceUpdate(claim="This mutation must not be accepted after activation."),
            )

        with session_scope(factory) as session:
            active_count = session.scalar(
                select(func.count())
                .select_from(ResumeVersionRecord)
                .where(
                    ResumeVersionRecord.profile_id == "demo-thomas",
                    ResumeVersionRecord.status == "active",
                )
            )
        assert active_count == 1
    finally:
        with factory.begin() as session:
            profile = session.get(CandidateProfileRecord, "demo-thomas")
            created = session.get(ResumeVersionRecord, draft.id)
            previous = session.get(ResumeVersionRecord, before.active_resume_version_id)
            assert profile is not None and created is not None and previous is not None
            created.status = "draft"
            session.flush()
            previous.status = "active"
            profile.active_resume_version_id = previous.id
            session.flush()
            session.delete(created)


def test_analysis_pins_database_version_and_fails_closed_mid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, retrieval = services()
    prepared = FallbackRetrievalBackend(retrieval, LocalRetrievalBackend()).prepare("demo-thomas")

    def unavailable(
        query: str, profile_id: str, version_id: str, limit: int = 3
    ) -> list[RankedEvidence]:
        raise RuntimeError("simulated transient failure")

    monkeypatch.setattr(retrieval, "search_version", unavailable)
    analysis = analyze_job(
        "Senior engineer role.\n"
        "Required: Build TypeScript and React applications across complex systems.\n"
        "Lead cross-functional delivery and mentor other engineers.",
        "demo-thomas",
        backend=prepared,
    )

    assert analysis.evidence
    assert all(not assessment.evidence_ids for assessment in analysis.assessments)
