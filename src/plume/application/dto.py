"""Use-case inputs and outputs (plain dataclasses)."""

from dataclasses import dataclass

from plume.domain.knowledge.api import ApiId
from plume.domain.shared.ids import BuildId


@dataclass(frozen=True, slots=True)
class ImportResult:
    api_id: ApiId
    build_id: BuildId
    created: bool
    already_sealed: bool
    documents: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EmbedResult:
    chunks: int
    from_cache: int
    embedded: int


@dataclass(frozen=True, slots=True)
class TagResult:
    api_id: ApiId
    tag: str
    build_id: BuildId
    previous: BuildId | None


@dataclass(frozen=True, slots=True)
class GateSummary:
    passed: bool
    message: str
    metrics: dict[str, float | int]
    baseline: str | None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    api_id: ApiId
    build_id: BuildId
    reused: bool
    documents: int
    chunks: int
    embedded: int
    from_cache: int
    facts: int
    tag: TagResult | None
    gate: GateSummary | None = None
