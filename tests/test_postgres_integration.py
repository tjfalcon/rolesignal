import os

import pytest

from api.analyzer import analyze_job, load_fixture_corpus
from api.database import create_database_engine
from api.retrieval_backends import PostgresRetrievalBackend

DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is not configured")


def postgres_backend() -> PostgresRetrievalBackend:
    assert DATABASE_URL is not None
    return PostgresRetrievalBackend(create_database_engine(DATABASE_URL))


def test_seeded_evidence_round_trips_with_source_locators() -> None:
    backend = postgres_backend()

    stored = backend.load_corpus("demo-thomas")

    assert len(stored) == len(load_fixture_corpus("demo-thomas"))
    assert all(item.source_locator and item.visibility == "public" for item in stored)
    assert backend.database_status() == "postgres-ready"


def test_postgres_hybrid_search_returns_python_evidence() -> None:
    ranked = postgres_backend().search(
        "Build Python prototypes with machine learning engineers",
        "demo-thomas",
        limit=5,
    )

    assert "ghost-python" in {item.evidence.id for item in ranked}
    assert all(item.method == "postgres-fts-pgvector-rrf" for item in ranked)


def test_analysis_citations_resolve_through_postgres() -> None:
    backend = postgres_backend()
    analysis = analyze_job(
        "Senior application engineer.\n"
        "Required: Build Python services and collaborate with machine-learning engineers.\n"
        "Lead cross-functional delivery with product and engineering stakeholders.",
        "demo-thomas",
        backend=backend,
    )

    evidence_ids = {item.id for item in analysis.evidence}
    cited_ids = {evidence_id for item in analysis.assessments for evidence_id in item.evidence_ids}
    assert analysis.metrics.mode == "postgres-hybrid"
    assert cited_ids
    assert cited_ids <= evidence_ids
