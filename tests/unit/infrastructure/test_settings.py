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


def test_evidence_budget_is_a_setting() -> None:
    from plume.bootstrap.container import Container  # noqa: PLC0415

    assert Settings().evidence_budget_chars == 200_000
    c = Container(settings=Settings(embedder="hash", evidence_budget_chars=500_000))
    assert c.generate()._budget == 500_000


def test_lists_accept_json_or_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUME_MCP_ALLOWED_HOSTS", "plume.example.com, plume.example.com:443")
    monkeypatch.setenv("PLUME_CORS_ORIGINS", '["https://a.example","https://b.example"]')
    monkeypatch.setenv("PLUME_MAINTAINER_TOKENS", "pl_token_aaaaaaaaaaaa,pl_token_bbbbbbbbbbbb")
    s = Settings()
    assert s.mcp_allowed_hosts == ("plume.example.com", "plume.example.com:443")
    assert s.cors_origins == ("https://a.example", "https://b.example")
    assert [t.get_secret_value() for t in s.maintainer_tokens] == [
        "pl_token_aaaaaaaaaaaa", "pl_token_bbbbbbbbbbbb",
    ]  # fmt: skip


def test_a_kubernetes_service_link_is_refused_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError  # noqa: PLC0415

    monkeypatch.setenv("PLUME_API_PORT", "tcp://10.96.0.12:18480")
    with pytest.raises(ValidationError, match="enableServiceLinks: false"):
        Settings()


def test_fusion_follows_the_embedder_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from plume.domain.knowledge.ranking import SEMANTIC_FUSION, Fusion  # noqa: PLC0415

    assert Settings(embedder="hash").fusion() == Fusion()
    assert Settings(embedder="vertex").fusion() == SEMANTIC_FUSION
    monkeypatch.setenv("PLUME_SEARCH_RRF_K", "30")
    monkeypatch.setenv("PLUME_SEARCH_DENSE_WEIGHT", "2")
    assert Settings(embedder="vertex").fusion() == Fusion(k=30, dense_weight=2.0)
