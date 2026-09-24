import logging
from typing import Protocol, cast

from sqlalchemy import Engine, Select, select, text
from sqlalchemy.orm import Session, sessionmaker

from api.database import create_database_engine, create_session_factory, database_url, session_scope
from api.db_models import EvidenceRecord
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
        statement = (
            select(EvidenceRecord)
            .where(
                EvidenceRecord.profile_id == profile_id,
                EvidenceRecord.visibility == "public",
            )
            .order_by(EvidenceRecord.id)
        )
        with session_scope(self.session_factory) as session:
            records = session.scalars(statement).all()
        return [record_to_evidence(record) for record in records]

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        candidate_limit = max(limit * 4, 12)
        lexical = self._lexical_ranking(query, profile_id, candidate_limit)
        semantic = self._semantic_ranking(query, profile_id, candidate_limit)
        return reciprocal_rank_fusion(
            [lexical, semantic],
            method="postgres-fts-pgvector-rrf",
            limit=limit,
        )

    def _lexical_ranking(
        self, query: str, profile_id: str, limit: int
    ) -> list[CandidateEvidence]:
        statement = text(
            """
            SELECT id, profile_id, claim, skill_tags, skill_text, source,
                   source_locator, visibility, embedding, created_at, updated_at
            FROM candidate_evidence
            WHERE profile_id = :profile_id
              AND visibility = 'public'
              AND search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY ts_rank_cd(
                search_vector,
                websearch_to_tsquery('english', :query)
            ) DESC, id
            LIMIT :limit
            """
        )
        with session_scope(self.session_factory) as session:
            rows = session.execute(
                statement,
                {"profile_id": profile_id, "query": query, "limit": limit},
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
        self, query: str, profile_id: str, limit: int
    ) -> list[CandidateEvidence]:
        query_vector = local_embedding(query)
        distance = EvidenceRecord.embedding.cosine_distance(query_vector)
        statement: Select[tuple[EvidenceRecord]] = (
            select(EvidenceRecord)
            .where(
                EvidenceRecord.profile_id == profile_id,
                EvidenceRecord.visibility == "public",
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
            corpus = self.primary.load_corpus(profile_id)
            if corpus:
                return corpus
        except Exception as error:
            logger.warning("postgres corpus unavailable; using fixture fallback: %s", error)
        return self.fallback.load_corpus(profile_id)

    def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
        try:
            ranked = self.primary.search(query, profile_id, limit)
            if ranked:
                return ranked
        except Exception as error:
            logger.warning("postgres retrieval unavailable; using local fallback: %s", error)
        return self.fallback.search(query, profile_id, limit)

    def database_status(self) -> str:
        status = self.primary.database_status()
        return status if status == "postgres-ready" else "postgres-unavailable-local-fallback"


def create_retrieval_backend() -> RetrievalBackend:
    url = database_url()
    local = LocalRetrievalBackend()
    if not url:
        return local
    engine = create_database_engine(url)
    return FallbackRetrievalBackend(PostgresRetrievalBackend(engine), local)
