from pathlib import Path

import pytest

from plume.infrastructure.settings import Settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no stray .env
    for name in ("PLUME_DATABASE_URL", "PLUME_API_PORT", "PLUME_VERTEX_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_use_the_plume_port_block() -> None:
    settings = Settings()
    assert settings.database_url.hosts()[0]["port"] == 18432
    assert settings.api_port == 18480
    assert settings.mcp_port == 18481
    assert settings.vertex_api_key is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUME_DATABASE_URL", "postgresql+psycopg://u:p@db:5555/x")
    monkeypatch.setenv("PLUME_API_PORT", "18490")
    settings = Settings()
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@db:5555/x"
    assert settings.api_port == 18490


def test_secret_is_never_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUME_VERTEX_API_KEY", "not-a-real-key")
    settings = Settings()
    assert settings.vertex_api_key is not None
    assert "not-a-real-key" not in repr(settings)
    assert "not-a-real-key" not in str(settings.model_dump())


def test_dotenv_file_is_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PLUME_MCP_PORT=18482\n", encoding="utf-8")
    assert Settings().mcp_port == 18482
