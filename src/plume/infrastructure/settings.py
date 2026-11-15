"""Settings. This module is the ONLY place that reads environment variables.

All variables use the ``PLUME_`` prefix; a ``.env`` file in the working directory is read too.
Defaults match the local docker compose stack (Plume's port block is 18400-18499).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLUME_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+psycopg://plume:plume@127.0.0.1:18432/plume"),
        description="SQLAlchemy URL (psycopg 3 driver).",
    )
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=18480, ge=1, le=65535)
    mcp_port: int = Field(default=18481, ge=1, le=65535)
    vertex_api_key: SecretStr | None = Field(
        default=None,
        description="Vertex AI express key. Local use only; never logged.",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None, description="Gemini API (AI Studio) key. Never logged."
    )
    embedder: Literal["auto", "hash", "vertex", "gemini"] = Field(
        default="auto",
        description="auto = vertex if PLUME_VERTEX_API_KEY, else gemini if PLUME_GEMINI_API_KEY, "
        "else the offline hash embedder.",
    )
    embed_model: str = "gemini-embedding-001"
    embed_dims: Literal[768] = 768
    embed_batch_size: int | None = Field(default=None, ge=1, le=250)
    chunk_max_chars: int = Field(default=6000, ge=200)
    mcp_host: str = "127.0.0.1"
    mcp_public_url: str = Field(
        default="http://127.0.0.1:18481/mcp", description="MCP URL shown to users (connect hint)."
    )
    mcp_allowed_hosts: tuple[str, ...] = Field(
        default=("127.0.0.1:*", "localhost:*", "[::1]:*"),
        description="Host headers the MCP server accepts (DNS-rebinding protection).",
    )
    reader_rate_limit_per_minute: int = Field(default=120, ge=0)
    data_dir: Path = Field(
        default=Path(".plume"), description="Uploaded packages and dumps (maintainer jobs)."
    )
    gold_dirs: tuple[Path, ...] = Field(
        default=(), description="Directories of gold sets (<api>.json) for the eval gate."
    )
    gate_min_recall: float = Field(default=0.6, ge=0, le=1)
    gate_max_drop: float = Field(default=0.05, ge=0, le=1)
    maintainer_tokens: tuple[SecretStr, ...] = Field(
        default=(), description="Bearer tokens of maintainers (comma list in JSON). Never logged."
    )
    max_upload_bytes: int = Field(default=200 * 1024 * 1024, ge=1024)
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:18473", "http://localhost:18473")

    @property
    def sqlalchemy_url(self) -> str:
        return str(self.database_url)

    @property
    def resolved_embedder(self) -> Literal["hash", "vertex", "gemini"]:
        if self.embedder != "auto":
            return self.embedder
        if self.vertex_api_key is not None and self.vertex_api_key.get_secret_value():
            return "vertex"
        if self.gemini_api_key is not None and self.gemini_api_key.get_secret_value():
            return "gemini"
        return "hash"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
