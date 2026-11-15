"""Reader outputs. Every result names the build it was read from and its date."""

from dataclasses import dataclass, field

from plume.application.ports.eval_repo import EvalRecord
from plume.domain.knowledge.api import ApiInfo
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation
from plume.domain.knowledge.fact import FactKind


@dataclass(frozen=True, slots=True)
class BuildRef:
    api: str
    build: str
    tag: str | None
    docs_as_of: str


@dataclass(frozen=True, slots=True)
class TraceStep:
    source: str  # plume | postgres | gemini | embedder
    label: str
    ms: float


@dataclass(frozen=True, slots=True)
class ApiOverview:
    info: ApiInfo
    ref: BuildRef | None
    counts: dict[str, int]
    tags: tuple[str, ...]
    embed_model: str | None
    dims: int | None
    eval: EvalRecord | None = None


@dataclass(frozen=True, slots=True)
class SearchHit:
    doc_id: str
    kind: DocumentKind
    title: str
    subtitle: str
    snippet: str
    source_url: str | None
    dense_rank: int | None
    text_rank: int | None
    dense_score: float
    text_score: float
    fused: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    ref: BuildRef
    query: str
    mode: str
    hits: tuple[SearchHit, ...]
    trace: tuple[TraceStep, ...]
    total_ms: float


@dataclass(frozen=True, slots=True)
class FactMatch:
    kind: FactKind
    name: str
    owner_id: str
    owner_title: str | None
    resource: str | None
    location: FieldLocation | None
    type: str | None
    required: bool
    complete: bool
    citation: Citation


@dataclass(frozen=True, slots=True)
class FindFactResult:
    ref: BuildRef
    name: str
    found: bool
    matches: tuple[FactMatch, ...]
    complete: bool
    """False when any checked source is flagged partial: absence is then not proven."""
    checked: dict[str, int]
    text_mentions: tuple[SearchHit, ...]
    wording: str
    incomplete_sources: tuple[str, ...] = field(default=())
    reasons: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class DocumentResult:
    ref: BuildRef
    document: Document
    citation: Citation


@dataclass(frozen=True, slots=True)
class ParamCheck:
    name: str
    found: bool
    where: str | None


@dataclass(frozen=True, slots=True)
class CheckCallResult:
    ref: BuildRef
    method: str
    path: str
    verdict: str  # documented | not_documented
    complete: bool
    matched_id: str | None
    matched_method: str | None
    matched_path: str | None
    params: tuple[ParamCheck, ...]
    checked: dict[str, int]
    citation: Citation | None
