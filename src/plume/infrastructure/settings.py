"""Settings. This module is the ONLY place that reads environment variables.

All variables use the ``PLUME_`` prefix; a ``.env`` file in the working directory is read too.
Defaults match the local docker compose stack (Plume's port block is 18400-18499).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from plume.domain.knowledge.ranking import SEMANTIC_FUSION, Fusion

MIN_TOKEN_LENGTH = 16


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
    vertex_key_file: Path | None = Field(
        default=None,
        description="File holding the Vertex AI express key for server-side model generation "
        "(maintainer). Read on every call, never logged. Unset = generation answers 503.",
    )
    model_llm: str = Field(
        default="gemini-4-argon", description="Gemini model for server-side model generation."
    )
    model_max_rounds: int = Field(default=3, ge=1, le=10)
    evidence_budget_chars: int = Field(
        default=200_000,
        ge=20_000,
        le=2_000_000,
        description="Characters of API evidence server generation sends the model, shared "
        "fairly by the APIs (~4 characters per prompt token).",
    )
    vertex_project: str | None = Field(
        default=None,
        description="Google Cloud project (id or number) for server-side generation: with it Plume "
        "calls the model at PLUME_VERTEX_LOCATION (some models, e.g. gemini-4-argon, answer only "
        "at 'global'); without it the location-less express URL.",
    )
    vertex_location: str = Field(default="global", pattern=r"^[a-z0-9-]{2,40}$")
    vertex_auth: Literal["auto", "key", "adc"] = Field(
        default="auto",
        description="How Plume authenticates to Vertex: key = PLUME_VERTEX_API_KEY / "
        "PLUME_VERTEX_KEY_FILE; adc = Application Default Credentials (Workload Identity on "
        "GKE), which needs PLUME_VERTEX_PROJECT; auto = a key when one is configured, else ADC "
        "when a project is set.",
    )
    vertex_embed_location: str = Field(
        default="global",
        pattern=r"^[a-z0-9-]{2,40}$",
        description="Location of the embedding model on the project URL (used whenever "
        "PLUME_VERTEX_PROJECT is set, with a key or ADC), e.g. europe-west3 to keep query text "
        "in the EU; 'eu' / 'us' use the multi-region endpoints (aiplatform.eu.rep.googleapis.com, "
        "needed for gemini-embedding-2). Without a project a key uses the express URL.",
    )
    trusted_proxy_hops: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Behind N trusted proxies that append to X-Forwarded-For, the rate limiter "
        "takes the client address N entries from the right. 0 = the TCP peer (no proxy).",
    )
    mcp_app_html: Path | None = Field(
        default=None,
        description="The MCP App bundle (model view, one self-contained HTML file). Unset = the "
        "file packaged with Plume.",
    )
    web_public_url: str | None = Field(
        default=None,
        description="The web UI's public base URL; model share links are <this>/models/{id}.",
    )
    reports: bool = Field(
        default=False,
        description="PLUME_REPORTS=on gives readers' LLMs the tools to report questions Plume "
        "could not answer (find_reported_questions, report_question, add_to_report). Off by "
        "default: on in dev; in prod only after the owner's go and a privacy notice.",
    )
    reports_retention_days: int = Field(
        default=90, ge=1, le=3650, description="Open reports untouched this long are purged."
    )
    reports_per_hour: int = Field(
        default=10, ge=1, le=1000, description="Reports and notes per session per hour."
    )
    reports_duplicate_similarity: float = Field(
        default=0.92,
        ge=0.5,
        le=1.0,
        description="A new report this similar (cosine) to an existing one becomes a note on it.",
    )
    reports_salt: SecretStr | None = Field(
        default=None,
        description="Key for the session-id hash; unset = random per process (sessions do not "
        "link across restarts). Never logged.",
    )
    reports_keep_error_codes: bool = Field(
        default=True,
        description="Keep 7-8 digit runs right after 'error' / 'code' / 'errorCode' in reports "
        "(the owner's choice); off = redacted like any long digit run.",
    )
    reports_keep_rpc_method: bool = Field(
        default=True,
        description="Keep the value of an RPC selector `method=...` (the owner's choice).",
    )
    embed_model: str = "gemini-embedding-001"
    embed_prompt: Literal["none", "gemini"] = Field(
        default="none",
        description="gemini = write the task into the text, Google's documented format for "
        "gemini-embedding-2 (documents 'title: … | text: …', queries 'task: search result | "
        "query: …'); builds record the model as '<model>+prompt'. gemini-embedding-2 only.",
    )
    embed_dims: Literal[768] = 768
    embed_batch_size: int | None = Field(default=None, ge=1, le=250)
    # Parallel embedding requests (Vertex gemini-embedding-001 takes one text per request).
    embed_concurrency: int = Field(default=8, ge=1, le=32)
    chunk_max_chars: int = Field(default=6000, ge=200)
    mcp_host: str = "127.0.0.1"
    mcp_public_url: str = Field(
        default="http://127.0.0.1:18481/mcp", description="MCP URL shown to users (connect hint)."
    )
    mcp_allowed_hosts: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("127.0.0.1:*", "localhost:*", "[::1]:*"),
        description="Host headers the MCP server accepts (DNS-rebinding protection).",
    )
    reader_rate_limit_per_minute: int = Field(default=120, ge=0)
    data_dir: Path = Field(
        default=Path(".plume"), description="Uploaded packages and dumps (maintainer jobs)."
    )
    gold_dirs: Annotated[tuple[Path, ...], NoDecode] = Field(
        default=(), description="Directories of gold sets (<api>.json) for the eval gate."
    )
    gate_min_recall: float = Field(default=0.6, ge=0, le=1)
    model_gold_dirs: Annotated[tuple[Path, ...], NoDecode] = Field(
        default=(),
        description="Directories of model gold files (plume.model-gold.v1) for model-eval and "
        "the release gate of official models.",
    )
    model_gate_min_recall: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Recall a model needs against its gold to be released (unset: only "
        "invented = 0 is required).",
    )
    gate_max_drop: float = Field(default=0.05, ge=0, le=1)
    search_rrf_k: int | None = Field(
        default=None,
        ge=1,
        description="Hybrid search RRF k. Default: 10 with a real embedding model, 60 with the "
        "offline hash embedder.",
    )
    search_dense_weight: float | None = Field(
        default=None,
        gt=0,
        description="Weight of the dense (embedding) ranking in hybrid search; full text weighs "
        "1. Default: 5 with a real embedding model, 1 with the offline hash embedder.",
    )
    gate_source: Literal["combined", "docs", "spec"] = Field(
        default="combined",
        description="Which gold questions the recall floor reads (a set without questions of "
        "that source falls back to combined). The regression check covers each source.",
    )
    gate_min_recall_by_embedder: dict[str, float] = Field(
        default_factory=dict,
        description='Per-embedder recall floor, e.g. {"vertex": 0.75}; others use '
        "PLUME_GATE_MIN_RECALL (0.6, set for the offline hash embedder).",
    )
    maintainer_tokens: Annotated[tuple[SecretStr, ...], NoDecode] = Field(
        default=(), description="Bearer tokens of maintainers (comma list in JSON). Never logged."
    )
    max_upload_bytes: int = Field(default=200 * 1024 * 1024, ge=1024)
    mcp_debug: bool = Field(
        default=False,
        description="Log each MCP request's JSON-RPC method (initialize: client and whether it "
        "declared MCP Apps; resources/read of ui://; tools/call names). No arguments or results.",
    )
    mcp_cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(),
        description="Browser origins allowed to call the MCP endpoints (for browser-based MCP "
        "clients such as the ext-apps basic-host). Empty = no CORS (Claude web/Desktop/Code "
        "connect without it).",
    )
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:18473",
        "http://localhost:18473",
    )

    @field_validator(
        "mcp_allowed_hosts",
        "gold_dirs",
        "model_gold_dirs",
        "maintainer_tokens",
        "mcp_cors_origins",
        "cors_origins",
        mode="before",
    )
    @classmethod
    def _list_or_commas(cls, value: Any) -> Any:
        """A JSON list (["a","b"]) or a comma-separated string (a,b): container platforms
        make plain strings easier than JSON."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @field_validator("api_port", "mcp_port", mode="before")
    @classmethod
    def _not_a_service_link(cls, value: Any) -> Any:
        """Kubernetes injects PLUME_API_PORT=tcp://10.0.0.1:18480 for a Service named
        plume-api (service links), which collides with Plume's PLUME_ prefix."""
        if isinstance(value, str) and "://" in value:
            raise ValueError(
                f"{value!r} looks like a Kubernetes service link (a Service named plume-api or "
                "plume-mcp): set enableServiceLinks: false on the pod, or name the Service "
                "differently, or set the port explicitly"
            )
        return value

    @field_validator("maintainer_tokens")
    @classmethod
    def _strong_tokens(cls, tokens: tuple[SecretStr, ...]) -> tuple[SecretStr, ...]:
        for t in tokens:
            value = t.get_secret_value()
            if len(value) < MIN_TOKEN_LENGTH or value != value.strip():
                raise ValueError(
                    f"maintainer tokens must be at least {MIN_TOKEN_LENGTH} characters, no spaces"
                )
        return tokens

    @property
    def sqlalchemy_url(self) -> str:
        return str(self.database_url)

    def vertex_key(self) -> str | None:
        """The Vertex key: PLUME_VERTEX_API_KEY, else the file PLUME_VERTEX_KEY_FILE (read here,
        never logged), so a container can mount the key instead of carrying it in its env."""
        if self.vertex_api_key is not None and self.vertex_api_key.get_secret_value():
            return self.vertex_api_key.get_secret_value()
        if self.vertex_key_file is not None and self.vertex_key_file.is_file():
            key = self.vertex_key_file.read_text(encoding="utf-8").strip()
            return key or None
        return None

    def gate_floor(self) -> float:
        """The eval gate's recall floor for the embedder in use (per-embedder override)."""
        return self.gate_min_recall_by_embedder.get(self.resolved_embedder, self.gate_min_recall)

    def fusion(self) -> Fusion:
        """Hybrid search fusion for the embedder in use (env overrides either value)."""
        base = Fusion() if self.resolved_embedder == "hash" else SEMANTIC_FUSION
        return Fusion(
            k=self.search_rrf_k or base.k,
            dense_weight=self.search_dense_weight or base.dense_weight,
        )

    def vertex_uses_adc(self) -> bool:
        """Vertex through Application Default Credentials (no key; a project is required)."""
        if self.vertex_auth == "key":
            return False
        if self.vertex_auth == "adc":
            return True
        return not self.vertex_key() and bool(self.vertex_project)

    @property
    def resolved_embedder(self) -> Literal["hash", "vertex", "gemini"]:
        if self.embedder != "auto":
            return self.embedder
        if self.vertex_key():
            return "vertex"
        if self.gemini_api_key is not None and self.gemini_api_key.get_secret_value():
            return "gemini"
        return "hash"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
