"""Reader outputs. Every result names the build it was read from and its date."""

from dataclasses import dataclass, field
from typing import Any

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
    has_icon: bool = False


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
    constraints: dict[str, Any] | None = None
    note: str | None = None  # e.g. the header is the OAuth 2.0 standard, not the vendor's text


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
    note: str | None = None  # e.g. where this API's paging is described (not asserted)
    guide_id: str | None = None  # the guide the note points to


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
    alternatives: tuple[str, ...] = ()
    """Other operations documented at the same METHOD + path (distinct ids)."""
    matched_real_path: str | None = None  # the package's own path (fixed version), if any
    note: str | None = None  # why a path that matches a template is still not documented
    # ambiguous: the parameter that picks the operation, and (value, operation id) per option
    pick_param: str | None = None
    pick_options: tuple[tuple[str, str], ...] = ()
