"""HTTP request/response schemas (camelCase on the wire)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


ItemKind = Literal["endpoint", "model", "guide", "auth", "app"]
KindFilter = Literal["all", "endpoint", "model", "guide", "auth", "app"]
SearchMode = Literal["hybrid", "dense", "text"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ErrorBody(Schema):
    error: str
    message: str
    detail: str


class ApiStatus(Schema):
    kind: Literal["ready", "unpublished"]
    recall_at5: float | None = Field(
        default=None, description="From the eval gate (slice 4); null until evaluated."
    )


class Logo(Schema):
    text: str
    color: str
    url: str | None = None


class ApiSummary(Schema):
    id: str
    name: str
    category: str
    summary: str
    endpoints: int
    models: int
    model_shapes: int = Field(description="Distinct model structures (same schema = one shape).")
    model_names: int = Field(description="Distinct model names (bundle roots excluded).")
    guides: int
    docs_as_of: str | None
    status: ApiStatus
    logo: Logo


class ApiList(Schema):
    items: list[ApiSummary]


class IndexInfo(Schema):
    embedding: str | None
    dimensions: int | None
    store: str
    build: str | None


class Connect(Schema):
    claude_code: str
    mcp_url: str


class Quality(Schema):
    recall_at5: float
    mrr: float
    citation_hit_rate: float
    fact_accuracy: float
    invented_endpoints: int | None = Field(
        default=None, description="Not measured yet (Level 2 with Claude); always null."
    )
    missing_expected: int
    gold_questions: int
    gate_passed: bool
    evaluated_at: str


class ApiDetail(ApiSummary):
    chunks: int
    is_live: bool
    tag: str | None
    tags: list[str]
    versions: list[str]
    doc_link: str | None
    quality: Quality | None = Field(default=None, description="Null until the eval gate runs.")
    index: IndexInfo
    connect: Connect


class BrowseItem(Schema):
    id: str
    kind: ItemKind
    title: str
    method: str | None = None
    path: str | None = None
    resource: str | None = None
    deprecated: bool = False


class BrowseResult(Schema):
    build: str
    items: list[BrowseItem]
    total: int


class TraceStep(Schema):
    source: str
    label: str
    ms: float


class SearchRequest(Schema):
    query: str = Field(min_length=1, max_length=2000)
    mode: SearchMode = "hybrid"
    kind: KindFilter = "all"
    top_k: int = Field(default=8, ge=1, le=50)
    version: str | None = Field(default=None, description="Tag or build id; default latest.")


class SearchHit(Schema):
    id: str
    kind: ItemKind
    title: str
    subtitle: str
    snippet: str
    source_url: str | None
    dense_rank: int | None
    text_rank: int | None
    dense_score: float
    text_score: float
    fused: float


class SearchResponse(Schema):
    api: str
    build: str
    docs_as_of: str
    results: list[SearchHit]
    trace: list[TraceStep]
    total_ms: float
    claude_payload: str


class AskRequest(Schema):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    version: str | None = None


class Passage(Schema):
    id: str
    title: str
    quote: str
    source_url: str | None


class AskResponse(Schema):
    api: str
    build: str
    docs_as_of: str
    question: str
    passages: list[Passage]
    trace: list[TraceStep]
    total_ms: float


class CheckCallRequest(Schema):
    method: HttpMethod
    path: str = Field(min_length=1, max_length=1000)
    params: list[str] = Field(default_factory=list, max_length=100)
    version: str | None = None


class MatchedEndpoint(Schema):
    id: str
    method: str
    path: str


class ParamCheck(Schema):
    name: str
    found: bool
    where: str | None


class Checked(Schema):
    endpoints: int
    models: int


class Citation(Schema):
    doc_id: str
    source_url: str | None
    anchor: str | None
    quote: str | None


class CheckCallResponse(Schema):
    api: str
    build: str
    verdict: Literal["documented", "not_documented"]
    complete: bool
    matched: MatchedEndpoint | None
    param_checks: list[ParamCheck]
    checked: Checked
    evidence: Citation | None


class FindFactRequest(Schema):
    name: str = Field(min_length=1, max_length=300)
    kind: Literal["endpoint", "field", "scope"] | None = None
    owner: str | None = Field(default=None, description="Document id to look in.")
    resource: str | None = None
    location: Literal["path", "query", "header", "body", "response", "model"] | None = None
    version: str | None = None


class FactMatch(Schema):
    kind: str
    name: str
    owner_id: str
    owner_title: str | None
    resource: str | None
    location: str | None
    type: str | None
    required: bool
    complete: bool
    evidence: Citation


class FindFactResponse(Schema):
    api: str
    build: str
    docs_as_of: str
    name: str
    found: bool
    complete: bool
    checked: Checked
    matches: list[FactMatch]
    incomplete_sources: list[str]
    incomplete_reasons: list[str] = Field(default_factory=list)
    text_mentions: list[SearchHit]
    wording: str


class FieldOut(Schema):
    name: str
    location: str
    type: str | None
    required: bool
    description: str | None


class DocumentOut(Schema):
    api: str
    build: str
    docs_as_of: str
    id: str
    kind: ItemKind
    title: str
    resource: str | None
    method: str | None
    path: str | None
    deprecated: bool
    complete: bool
    source_url: str | None
    anchor: str | None
    text: str
    fields: list[FieldOut]
    scopes: list[str]


class BuildOut(Schema):
    id: str
    status: Literal["draft", "sealed"]
    created_at: str
    sealed_at: str | None
    items: int
    content_hash: str | None
    tags: list[str]
    embed_model: str | None
    package_hash: str | None


class BuildList(Schema):
    api: str
    items: list[BuildOut]


class DiffOut(Schema):
    api: str
    from_build: str
    to_build: str
    added: list[str]
    changed: list[str]
    removed: list[str]
    unchanged: int


class Health(Schema):
    status: Literal["ok"]
    version: str


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True)


class Me(Schema):
    name: str


class ReviewRequest(Schema):
    api_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=200)
    tag: str = Field(default="latest", min_length=1, max_length=64)


class JobOut(BaseModel):
    """A maintainer job (keys are camelCase as listed)."""

    model_config = ConfigDict(extra="allow")
    id: str
    apiId: str  # noqa: N815 - wire name
    displayName: str  # noqa: N815
    status: Literal[
        "uploaded", "reviewed", "building", "staged", "failed", "published", "discarded"
    ]
    tag: str
    liveBuild: str | None  # noqa: N815
    stagedBuild: str | None  # noqa: N815
    package: dict[str, Any]
    diff: dict[str, Any] | None
    plan: dict[str, Any] | None
    eval: dict[str, Any] | None
    error: str | None


class SuggestRequest(Schema):
    apis: list[str] = Field(min_length=2, max_length=6)


class ApiRef(Schema):
    id: str
    name: str
    short_name: str
    logo: Logo
    build: str | None = None


class Difficulty(Schema):
    tone: Literal["ok", "warn", "bad"]
    label: str


class Concept(Schema):
    id: str
    name: str
    description: str
    likely_fields: int
    coverage: dict[str, Literal["direct", "derived", "absent"]]
    operations: list[Literal["read", "write"]]
    difficulty: Difficulty
    documents: dict[str, list[str]]


class NotModeled(Schema):
    count: int
    summary: str


class SuggestResponse(Schema):
    apis: list[ApiRef]
    concepts: list[Concept]
    not_modeled: NotModeled


class GenerateRequest(Schema):
    apis: list[str] = Field(min_length=2, max_length=6)
    concept: str = Field(min_length=1, max_length=100)


class PinnedInput(Schema):
    api: str
    build: str


class GenerateResponse(Schema):
    session_id: str
    status: Literal["awaiting_draft", "ready"]
    snapshot_id: str | None
    inputs: list[PinnedInput]
    context_url: str
    claude_prompt: str
    mcp_url: str
    maintainer_mcp_url: str


class DraftIssue(Schema):
    code: str
    field: str
    api: str | None
    message: str


class DraftRefused(Schema):
    error: str
    message: str
    accepted: bool
    issues: list[DraftIssue]


class ModelListItem(Schema):
    id: str
    name: str
    concept: str
    apis: list[str]
    generated_at: str


class ModelList(Schema):
    items: list[ModelListItem]
