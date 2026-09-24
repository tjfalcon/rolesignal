import logging
from typing import Protocol, cast

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from api.database import create_database_engine, create_session_factory, database_url, session_scope
from api.db_models import CandidateProfileRecord, EvidenceRecord
from api.models import CandidateEvidence
from api.retrieval import (
    RankedEvidence,
    hybrid_search,
    local_embedding,
    reciprocal_rank_fusion,
)

logger = logging.getLogger("rolesignal.retrieval")


class RetrievalBackend(Protocol):
    mode: str

    def load_corpus(self, profile_id: str) -> list[CandidateEvidence]: ...

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]: ...

    def database_status(self) -> str: ...


def record_to_evidence(record: EvidenceRecord) -> CandidateEvidence:
    return CandidateEvidence(
        id=record.id,
        claim=record.claim,
        skill_tags=record.skill_tags,
        source=record.source,
        source_locator=record.source_locator,
        visibility=record.visibility,
    )


class LocalRetrievalBackend:
    mode = "deterministic"

    def load_corpus(self, profile_id: str) -> list[CandidateEvidence]:
        from api.analyzer import load_fixture_corpus

        return load_fixture_corpus(profile_id)

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        return hybrid_search(query, self.load_corpus(profile_id), limit=limit)

    def database_status(self) -> str:
        return "in-memory-demo"


class PostgresRetrievalBackend:
    mode = "postgres-hybrid"

    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory or create_session_factory(engine)

    def load_corpus(self, profile_id: str) -> list[CandidateEvidence]:
        version_id = self.active_version_id(profile_id)
        return self.load_version_corpus(profile_id, version_id) if version_id else []

    def active_version_id(self, profile_id: str) -> str | None:
        statement = select(CandidateProfileRecord.active_resume_version_id).where(
            CandidateProfileRecord.id == profile_id
        )
        with session_scope(self.session_factory) as session:
            return session.scalar(statement)

    def load_version_corpus(self, profile_id: str, version_id: str) -> list[CandidateEvidence]:
        statement = (
            select(EvidenceRecord)
            .where(
                EvidenceRecord.profile_id == profile_id,
                EvidenceRecord.resume_version_id == version_id,
                EvidenceRecord.visibility == "public",
                EvidenceRecord.approved.is_(True),
            )
            .order_by(EvidenceRecord.id)
        )
        with session_scope(self.session_factory) as session:
            records = session.scalars(statement).all()
        return [record_to_evidence(record) for record in records]

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        version_id = self.active_version_id(profile_id)
        return self.search_version(query, profile_id, version_id, limit) if version_id else []

    def search_version(
        self, query: str, profile_id: str, version_id: str, limit: int = 3
    ) -> list[RankedEvidence]:
        candidate_limit = max(limit * 4, 12)
        lexical = self._lexical_ranking(query, profile_id, version_id, candidate_limit)
        semantic = self._semantic_ranking(query, profile_id, version_id, candidate_limit)
        return reciprocal_rank_fusion(
            [lexical, semantic],
            method="postgres-fts-pgvector-rrf",
            limit=limit,
        )

    def _lexical_ranking(
        self, query: str, profile_id: str, version_id: str, limit: int
    ) -> list[CandidateEvidence]:
        statement = text(
            """
            SELECT evidence.id, evidence.profile_id, evidence.claim, evidence.skill_tags,
                   evidence.skill_text, evidence.source, evidence.source_locator,
                   evidence.visibility, evidence.embedding, evidence.created_at,
                   evidence.updated_at
            FROM candidate_evidence AS evidence
            WHERE evidence.profile_id = :profile_id
              AND evidence.resume_version_id = :version_id
              AND evidence.visibility = 'public'
              AND evidence.approved = true
              AND evidence.search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY ts_rank_cd(
                evidence.search_vector,
                websearch_to_tsquery('english', :query)
            ) DESC, evidence.id
            LIMIT :limit
            """
        )
        with session_scope(self.session_factory) as session:
            rows = session.execute(
                statement,
                {
                    "profile_id": profile_id,
                    "version_id": version_id,
                    "query": query,
                    "limit": limit,
                },
            ).mappings()
            return [
                CandidateEvidence(
                    id=cast(str, row["id"]),
                    claim=cast(str, row["claim"]),
                    skill_tags=cast(list[str], row["skill_tags"]),
                    source=cast(str, row["source"]),
                    source_locator=cast(str, row["source_locator"]),
                    visibility=cast(str, row["visibility"]),
                )
                for row in rows
            ]

    def _semantic_ranking(
        self, query: str, profile_id: str, version_id: str, limit: int
    ) -> list[CandidateEvidence]:
        query_vector = local_embedding(query)
        distance = EvidenceRecord.embedding.cosine_distance(query_vector)
        statement = (
            select(EvidenceRecord)
            .where(
                EvidenceRecord.profile_id == profile_id,
                EvidenceRecord.resume_version_id == version_id,
                EvidenceRecord.visibility == "public",
                EvidenceRecord.approved.is_(True),
            )
            .order_by(distance, EvidenceRecord.id)
            .limit(limit)
        )
        with session_scope(self.session_factory) as session:
            records = session.scalars(statement).all()
        return [record_to_evidence(record) for record in records]

    def database_status(self) -> str:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM candidate_evidence LIMIT 1"))
            return "postgres-ready"
        except Exception:
            return "postgres-unavailable"


class FallbackRetrievalBackend:
    def __init__(self, primary: PostgresRetrievalBackend, fallback: LocalRetrievalBackend) -> None:
        self.primary = primary
        self.fallback = fallback
        self.mode = "postgres-hybrid-with-local-fallback"

    def load_corpus(self, profile_id: str) -> list[CandidateEvidence]:
        try:
            return self.primary.load_corpus(profile_id)
        except Exception as error:
            logger.warning("postgres corpus unavailable; using fixture fallback: %s", error)
        return self.fallback.load_corpus(profile_id)

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        try:
            return self.primary.search(query, profile_id, limit)
        except Exception as error:
            logger.warning("postgres retrieval unavailable; using local fallback: %s", error)
        return self.fallback.search(query, profile_id, limit)

    def database_status(self) -> str:
        status = self.primary.database_status()
        return status if status == "postgres-ready" else "postgres-unavailable-local-fallback"

    def prepare(self, profile_id: str) -> RetrievalBackend:
        """Pin one evidence source and resume version for an entire analysis."""
        try:
            version_id = self.primary.active_version_id(profile_id)
            if version_id is None:
                return PreparedPostgresRetrievalBackend(self.primary, profile_id, "", [])
            corpus = self.primary.load_version_corpus(profile_id, version_id)
            return PreparedPostgresRetrievalBackend(self.primary, profile_id, version_id, corpus)
        except Exception as error:
            logger.warning("postgres analysis unavailable; selecting fixture fallback: %s", error)
            return self.fallback


class PreparedPostgresRetrievalBackend:
    mode = "postgres-hybrid"

    def __init__(
        self,
        primary: PostgresRetrievalBackend,
        profile_id: str,
        version_id: str,
        corpus: list[CandidateEvidence],
    ) -> None:
        self.primary = primary
        self.profile_id = profile_id
        self.version_id = version_id
        self.corpus = corpus

    def load_corpus(self, profile_id: str) -> list[CandidateEvidence]:
        return self.corpus if profile_id == self.profile_id else []

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        if profile_id != self.profile_id or not self.version_id:
            return []
        try:
            return self.primary.search_version(query, profile_id, self.version_id, limit)
        except Exception as error:
            logger.warning("pinned postgres retrieval failed closed: %s", error)
            return []

    def database_status(self) -> str:
        return self.primary.database_status()


def create_retrieval_backend() -> RetrievalBackend:
    url = database_url()
    local = LocalRetrievalBackend()
    if not url:
        return local
    engine = create_database_engine(url)
    return FallbackRetrievalBackend(PostgresRetrievalBackend(engine), local)
