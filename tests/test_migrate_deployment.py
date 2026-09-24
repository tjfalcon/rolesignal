import os
from unittest.mock import Mock

import pytest

from scripts import migrate_deployment


def test_skips_outside_vercel_deployment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    upgrade = Mock()
    monkeypatch.setattr("scripts.migrate_deployment.command.upgrade", upgrade)

    migrate_deployment.main()

    upgrade.assert_not_called()
    assert "Skipping deployment migration" in capsys.readouterr().out


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_requires_unpooled_url(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("VERCEL_ENV", environment)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL_UNPOOLED is required"):
        migrate_deployment.main()


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_migrates_deployment_with_direct_connection(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    direct_url = "postgresql://role:secret@direct.example.test/app?sslmode=require"
    monkeypatch.setenv("VERCEL_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", "postgresql://pooler.example.test/app")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", direct_url)
    upgrade = Mock()
    monkeypatch.setattr("scripts.migrate_deployment.command.upgrade", upgrade)

    migrate_deployment.main()

    assert os.environ["DATABASE_URL"] == direct_url
    upgrade.assert_called_once()
    config, revision = upgrade.call_args.args
    assert config.config_file_name == "alembic.ini"
    assert revision == "head"
