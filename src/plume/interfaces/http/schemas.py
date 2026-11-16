"""HTTP request/response schemas (camelCase on the wire)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


ItemKind = Literal["endpoint", "model", "guide", "auth", "trigger", "app"]
KindFilter = Literal["all", "endpoint", "model", "guide", "auth", "trigger", "app"]
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


class DocsUpdated(Schema):
    build: str
    at: str = Field(description="docsAsOf of that build")
    confirmed: int
    likely: int
    breaking: int


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
    docs_updated: DocsUpdated | None = Field(
        default=None,
        description="The latest build's visible docs changes (confirmed + likely, wording-only "
        "excluded); null when it has none or no release notes.",
    )


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


class SectionCounts(Schema):
    auth: int
    triggers: int
    webhook_endpoints: int


class SourceRef(Schema):
    url: str
    kind: str = Field(description="docs | spec | changelog | sdk | other")
    fetched_at: str | None = None


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
    sections: SectionCounts | None = Field(
        default=None, description="What the package contains: auth schemes, triggers, webhooks."
    )
    sources: list[SourceRef] | None = Field(
        default=None,
        description="Where the build's package came from (http(s) urls only). Null when the "
        "build has no recorded package metadata (older builds).",
    )
    extracted_at: str | None = Field(default=None, description="When stream extracted it.")


class BrowseItem(Schema):
    id: str
    kind: ItemKind
    title: str
    method: str | None = None
    path: str | None = None
    resource: str | None = None
    deprecated: bool = False
    tags: list[str] = Field(default_factory=list, description="The package's tags, verbatim.")


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


class KeepRequest(Schema):
    note: str | None = Field(default=None, max_length=500)


class RollbackRequest(Schema):
    reason: str = Field(min_length=1, max_length=500)


class PromoteRequest(Schema):
    quote: str = Field(min_length=1, max_length=2000)


class ReleaseRequest(Schema):
    supersedes: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Official models of the same concept this release replaces (ids from "
        "GET /v1/models/{id}/supersedable).",
    )


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
    alternatives: list[str] = Field(
        default_factory=list,
        description="Other operations documented at the same METHOD + path (their ids).",
    )


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
    tags: list[str] = Field(default_factory=list)
    responses: list[dict[str, Any]] = Field(
        default_factory=list, description="Endpoint responses[] from the package, verbatim."
    )
    errors: list[dict[str, Any]] = Field(
        default_factory=list, description="Endpoint errors[] from the package, verbatim."
    )
    raw: dict[str, Any] | None = Field(
        default=None, description="The package's source JSON for this item, verbatim."
    )
    raw_truncated: bool = Field(
        default=False, description="True when raw was over 256 KB and is omitted."
    )


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
    generation: bool = Field(
        description="Server-side model generation is configured (a model key is readable): "
        "POST /v1/models/generate with engine server will not answer 503 llm_unavailable."
    )


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
    q: str | None = Field(
        default=None, max_length=200, description="Text filter over name, id and reason."
    )
    only: Literal["multi", "single", "all"] = Field(
        default="multi",
        description="multi = in 2+ selected APIs; single = in exactly one; all = both.",
    )
    require: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="API ids (among `apis`) where the concept must be direct or derived.",
    )
    in_all: bool = Field(default=False, description="Only concepts present in every API.")
    write_only: bool = Field(default=False, description="Only concepts with write endpoints.")
    limit: int = Field(default=24, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ApiRef(Schema):
    id: str
    name: str
    short_name: str
    logo: Logo
    build: str | None = None


class Difficulty(Schema):
    tone: Literal["ok", "warn", "bad"]
    label: str


class ApiConceptCounts(Schema):
    models: int = Field(description="Model documents of this concept in the API.")
    endpoints: int = Field(description="Endpoints of this resource in the API.")
    operations: list[Literal["read", "create", "update", "delete"]]
    fields: int = Field(description="Distinct body/response field names of those documents.")


class Concept(Schema):
    id: str
    name: str
    reason: str = Field(
        description="One factual paragraph built from the builds (no LLM): what each API "
        "documents, how many fields are likely to map, and the difficulty."
    )
    api_counts: dict[str, ApiConceptCounts]
    likely_fields: int
    coverage: dict[str, Literal["direct", "derived", "absent"]]
    operations: list[Literal["read", "write"]]
    difficulty: Difficulty
    documents: dict[str, list[str]]


class NotModeled(Schema):
    count: int
    summary: str


class SuggestCounts(Schema):
    all: int = Field(description="Concepts in 2+ APIs matching q + require.")
    in_all: int
    write: int
    single: int = Field(description="Concepts in exactly one API matching q + require.")


class SuggestResponse(Schema):
    apis: list[ApiRef]
    concepts: list[Concept]
    total: int = Field(description="Concepts matching every filter (all pages).")
    limit: int
    offset: int
    next_offset: int | None
    counts: SuggestCounts
    not_modeled: NotModeled


class GenerateRequest(Schema):
    apis: list[str] = Field(min_length=2, max_length=6)
    concept: str = Field(min_length=1, max_length=100)
    engine: Literal["claude", "server"] | None = Field(
        default=None,
        description="claude = a session your Claude fills (default without the token); server = "
        "Plume generates it with its LLM (maintainer token; default with it).",
    )
    force: bool = Field(
        default=False, description="server engine: generate even if a model already exists."
    )


class ModelJobOut(Schema):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    apis: list[str]
    concept: str
    session_id: str | None
    round: int
    max_rounds: int
    snapshot_id: str | None
    error: str | None
    generator: str
    created_at: str
    updated_at: str
    events_url: str
    kind: Literal["model", "model_set"] = "model"
    set_id: str | None = None
    usage: dict[str, int] | None = Field(
        default=None, description="LLM tokens so far: {prompt, response, thoughts?, total}."
    )


class SessionStatus(Schema):
    session_id: str
    status: Literal["open", "submitted"]
    snapshot_id: str | None
    visibility: str | None
    apis: list[str]
    concept: str
    based_on: str | None


class RevisedSession(Schema):
    session_id: str
    based_on: str
    concept: str
    inputs: list["PinnedInput"]
    starting_draft: dict[str, Any]
    claude_prompt: str
    context_url: str


class MineRequest(Schema):
    owner_keys: list[str] = Field(min_length=1, max_length=200)


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


class StaleInput(Schema):
    api: str
    pinned: str
    current: str | None


class ImpactSummary(Schema):
    status: str = Field(description="current | updated_unaffected | affected | unknown")
    affected_count: int
    breaking_count: int


class ModelListItem(Schema):
    impact: ImpactSummary | None = Field(
        default=None, description="What newer docs mean for its mappings (null: not computed)."
    )
    id: str
    name: str
    concept: str
    apis: list[str]
    generated_at: str
    stale: bool = Field(description="A pinned build is no longer the API's latest.")
    stale_inputs: list[StaleInput] = Field(default_factory=list)
    visibility: Literal["official", "unreleased", "unlisted", "discarded", "superseded"] = (
        "official"
    )
    official: bool = True
    version: int = 1
    versions: int = 1
    lineage_id: str = ""
    same_concept: list[str] = Field(
        default_factory=list,
        description="Other official models of the same concept over the same APIs (readable "
        "by id); the list shows the newest.",
    )


class CollectionLink(Schema):
    id: str
    url: str


class MergeRequest(Schema):
    sources: list[str] = Field(
        alias="from", min_length=1, max_length=20, description="The other My models links."
    )


class ModelList(Schema):
    items: list[ModelListItem]
    collections: list[CollectionLink] = Field(
        default_factory=list,
        description="POST /mine only (transition): the My models links the owner keys became.",
    )


class AuthVariable(Schema):
    name: str
    description: str | None
    type: str | None
    required: bool


class AuthScope(Schema):
    scope: str | None
    description: str | None


class AuthSchemeSummary(Schema):
    id: str
    doc_id: str
    name: str
    type: str | None = Field(description="authorizationType from the package, verbatim.")
    grant_type: str | None
    header_name: str | None
    query_param: str | None
    scopes: int
    variables: int


class AuthList(Schema):
    api: str
    build: str
    present: bool
    note: str | None
    schemes: list[AuthSchemeSummary]


class AuthSchemeDetail(Schema):
    api: str
    build: str
    id: str
    doc_id: str
    name: str
    type: str | None
    grant_type: str | None
    header_name: str | None
    query_param: str | None
    scopes: list[AuthScope]
    variables: list[AuthVariable]
    setup_steps: list[Any] | None = Field(description="setupSteps verbatim (objects as given).")
    token_lifetime: dict[str, Any] | None
    test_url: str | None
    scheme: dict[str, Any] = Field(description="The auth JSON from the package, verbatim.")
    variables_schema: dict[str, Any] | None = Field(
        description="The scheme's .variables.schema.json (JSON Schema), verbatim."
    )
    companions: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="The scheme's companion files by suffix, verbatim: e.g. "
        '"oauth-token-params": {"schema": …, "sample": …} (the OAuth token request params), '
        '"variables": {"schema": …, "sample": …}.',
    )
    file: str | None


class TriggerSummary(Schema):
    key: str | None
    doc_id: str
    title: str
    description: str | None
    resource: str | None
    delivery: str | None
    sync_endpoint_id: str | None = None


class EndpointRef(Schema):
    doc_id: str
    method: str | None
    path: str | None


class TriggerList(Schema):
    api: str
    build: str
    present: bool
    note: str | None
    total: int
    items: list[TriggerSummary]
    webhooks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="connector/triggers/webhooks/*.json (subscribe/unsubscribe/list endpoints, "
        "handshake, verification), verbatim; [] when the package has none.",
    )
    endpoint_refs: dict[str, EndpointRef | None] = Field(
        default_factory=dict,
        description="Every endpointId named by `webhooks` and by the events' syncEndpointId, "
        "resolved to the endpoint document (null when it is not in this build).",
    )


class TriggerDetail(TriggerSummary):
    api: str
    build: str
    source_url: str | None
    event: dict[str, Any] = Field(description="The event JSON from the package, verbatim.")


class EnvironmentsOut(Schema):
    api: str
    build: str
    present: bool
    note: str | None
    environments: list[dict[str, Any]] = Field(
        default_factory=list, description="app.json environments[], verbatim."
    )
    versioning: dict[str, Any] | None = Field(description="app.json apiVersioning, verbatim.")
    base_urls: list[str] | None
    variables_schema: dict[str, Any] | None = Field(
        description="connector/environment.variables.schema.json, verbatim."
    )


class McpOut(Schema):
    api: str
    build: str
    present: bool
    note: str | None
    servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="connector/mcp/: per server {id, server (servers/<id>.json), tools: [{tool, "
        "inputSchema, outputSchema}]}, verbatim. Docs-only APIs have none.",
    )


class SuggestRelatedRequest(Schema):
    apis: list[str] = Field(min_length=2, max_length=6)
    concept: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=24, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SetAlias(Schema):
    concept: str = Field(description="One of `concepts`.")
    names: dict[str, str] = Field(
        description="api id -> the concept's name in that API (e.g. woocommerce: variation)."
    )


class SetSessionRequest(Schema):
    apis: list[str] = Field(min_length=2, max_length=6)
    concepts: list[str] = Field(min_length=1, max_length=8)
    aliases: list[SetAlias] = Field(
        default_factory=list,
        max_length=8,
        description="Aliases the user ACCEPTED (from suggest-related): the member's evidence in "
        "that API is searched under the alias name; recorded on the set.",
    )


class RelationEditRequest(Schema):
    relations: list[dict[str, Any]] = Field(
        min_length=1,
        max_length=64,
        description="[{id, kind?, cardinality?, embed?, ref?, from?, to?, confirmed?}]: design "
        "changes for existing relations (their evidence stays).",
    )
