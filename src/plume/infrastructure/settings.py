"""Settings. This module is the ONLY place that reads environment variables.

All variables use the ``PLUME_`` prefix; a ``.env`` file in the working directory is read too.
Defaults match the local docker compose stack (Plume's port block is 18400-18499).
"""

from functools import lru_cache

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

    @property
    def sqlalchemy_url(self) -> str:
        return str(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
