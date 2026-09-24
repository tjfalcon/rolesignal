import pytest

from api.database import create_database_engine, database_url, normalize_database_url


def test_normalize_neon_postgresql_url_for_psycopg() -> None:
    url = "postgresql://role:secret@ep-example-pooler.us-east-1.aws.neon.tech/app?sslmode=require"

    assert normalize_database_url(url) == (
        "postgresql+psycopg://role:secret@ep-example-pooler.us-east-1.aws.neon.tech/"
        "app?sslmode=require"
    )


def test_normalize_legacy_postgres_url_for_psycopg() -> None:
    assert normalize_database_url("postgres://role:secret@example.test/app") == (
        "postgresql+psycopg://role:secret@example.test/app"
    )


def test_normalize_preserves_explicit_driver() -> None:
    url = "postgresql+psycopg://role:secret@example.test/app"

    assert normalize_database_url(url) == url


def test_database_url_reads_and_normalizes_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "  postgresql://role:secret@example.test/app  ")

    assert database_url() == "postgresql+psycopg://role:secret@example.test/app"


def test_database_url_returns_none_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert database_url() is None


def test_create_database_engine_uses_psycopg_driver() -> None:
    engine = create_database_engine("postgresql://role:secret@example.test/app")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.pool._pre_ping is True
    engine.dispose()
