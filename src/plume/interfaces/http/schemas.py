"""HTTP request/response schemas (camelCase on the wire)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_REAL_PATH = (
    "The package's own path when it fixes the API version (e.g. /vendor/orders/v1/"
    "purchaseOrders); null when the version is variable ({version} in `path`) or absent."
)


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


class RemoveApiIn(Schema):
    confirm: str = Field(description="The API id, typed again.")
    force: bool = Field(
        default=False,
        description="Retire official (-> superseded) and unreleased (-> discarded) models and "
        "sets that pin the API's builds, then remove.",
    )
    reason: str | None = Field(default=None, max_length=500)


class DisplayNameIn(Schema):
    name: str | None = Field(description="The display name (1-80 chars); null clears it.")


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
    name_source: str = Field(
        default="derived",
        description="Where `name` comes from: override (a maintainer set it) | package "
        "(app.json title/displayName) | derived (from the package's id).",
    )
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


TOP1 = "Top-1 hit rate: the share of questions whose answer ranks first."


class SourceQuality(Schema):
    source: str = Field(description="docs | spec | tester, or another label of the gold set")
    recall_at5: float
    mrr: float
    top1_rate: float = Field(description=TOP1)
    questions: int = Field(description="Search questions of this source.")


class RuleSource(Schema):
    rule_id: str
    text: str | None = Field(default=None, description="The rule's own text.")
    type: str | None = Field(default=None, description="The rule's type (effect, rule, ...).")
    line: str | None = Field(
        default=None, description="The rule's line exactly as in the document text."
    )
    urls: list[str] = Field(description="The rule's pages: sourceUrl, then sourceUrls.")


class EndpointLink(Schema):
    endpoint_id: str
    link_basis: str = Field(
        description="text (the unit names the endpoint) | page (same documentation page) | "
        "slug (matching names), from knowledge-export/unit-links.json"
    )


class Quality(Schema):
    recall_at5: float = Field(description="All search questions (docs and spec combined).")
    mrr: float
    top1_rate: float = Field(description=TOP1)
    fact_accuracy: float
    invented_endpoints: int | None = Field(
        default=None, description="Not measured yet (Level 2 with Claude); always null."
    )
    missing_expected: int
    gold_questions: int
    gate_passed: bool
    evaluated_at: str
    by_source: list[SourceQuality] = Field(
        default_factory=list,
        description="The same metrics per question source (docs, spec), for the sources the "
        "gold set has; the fields above are over all of them.",
    )
    note: str | None = Field(
        default=None,
        description='"Too few questions to measure; a sanity check only." when the gold set '
        "has fewer than 10 questions; null otherwise.",
    )


class SectionCounts(Schema):
    auth: int
    triggers: int
    webhook_endpoints: int


class SourceRef(Schema):
    url: str
    kind: str = Field(description="docs | spec | changelog | sdk | other")
    fetched_at: str | None = None


class PackageWarningOut(Schema):
    code: str = Field(description='The text before the first ":".')
    text: str = Field(description="The producer's warning, verbatim.")


class Notice(Schema):
    code: str = Field(description="The package warning code it comes from.")
    section: str = Field(description='Where it applies: "auth" or "environments".')
    text: str = Field(description="What to tell the user.")
    doc_ids: list[str] = Field(
        default_factory=list,
        description="Guides that explain it (auth / signing), to read with the document tools.",
    )


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
    rate_limits: list[dict[str, Any]] = Field(
        default_factory=list,
        description="app.json rateLimits[] verbatim (scope, group, limit, windowSeconds, "
        "algorithm, notes, ...); empty when the package states none.",
    )
    package_warnings: list[PackageWarningOut] | None = Field(
        default=None,
        description="manifest.json warnings, all of them. Only with a valid maintainer bearer "
        "token; the key is absent otherwise.",
    )
    notices: list[Notice] = Field(
        default_factory=list,
        description="User-facing notices for the warning codes Plume knows, with their section.",
    )


class BrowseItem(Schema):
    id: str
    kind: ItemKind
    title: str
    method: str | None = None
    path: str | None = None
    real_path: str | None = Field(default=None, description=_REAL_PATH)
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
    override_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Release over a failing model gold gate (recall below the threshold): why. "
        "Kept with the release (releaseOverride). Never overrides an invented mapping.",
    )


class SetReleaseRequest(Schema):
    override_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Release members over a failing model gold gate (never invented): why.",
    )


class CheckCallRequest(Schema):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, frozen=True, extra="forbid"
    )

    method: HttpMethod
    path: str = Field(min_length=1, max_length=1000)
    params: list[str] = Field(default_factory=list, max_length=100)
    query: list[str] = Field(
        default_factory=list, max_length=100, description="Query parameter names."
    )
    body: list[str] = Field(
        default_factory=list, max_length=100, description="Request body field names."
    )
    version: str | None = None


class MatchedEndpoint(Schema):
    id: str
    method: str
    path: str
    real_path: str | None = Field(default=None, description=_REAL_PATH)
    server: str | None = Field(
        default=None,
        description="The server whose base path the call carried and that was taken off to "
        "match (e.g. api_3: https://apim.ebay.com/commerce/media/v1_beta).",
    )


class ParamCheck(Schema):
    name: str
    found: bool
    where: str | None
    note: str | None = Field(
        default=None,
        description="When not found: e.g. the guide that describes this API's paging (to check).",
    )
    guide_id: str | None = Field(default=None, description="The guide the note points to.")


class Checked(Schema):
    endpoints: int
    models: int


class Citation(Schema):
    doc_id: str
    source_url: str | None
    anchor: str | None
    quote: str | None


class CallPickOption(Schema):
    value: str
    doc_id: str


class CallPick(Schema):
    param: str
    options: list[CallPickOption]


class CheckCallResponse(Schema):
    api: str
    build: str
    verdict: Literal["documented", "not_documented", "ambiguous"]
    complete: bool
    matched: MatchedEndpoint | None
    param_checks: list[ParamCheck]
    checked: Checked
    evidence: Citation | None
    alternatives: list[str] = Field(
        default_factory=list,
        description="Other operations documented at the same METHOD + path (their ids).",
    )
    note: str | None = Field(
        default=None,
        description="Why a path matching a template is not documented (e.g. another version).",
    )
    pick: CallPick | None = Field(
        default=None,
        description="ambiguous: the parameter whose value picks one of the operations sharing "
        "METHOD + path, and every value with its operation.",
    )


class FindFactRequest(Schema):
    name: str = Field(min_length=1, max_length=300)
    kind: Literal["endpoint", "field", "scope", "rate_limit"] | None = None
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
    constraints: dict[str, Any] | None = None
    note: str | None = Field(
        default=None,
        description="How to read the evidence, e.g. the header is the OAuth 2.0 standard "
        "(RFC 6750), not stated in the vendor's docs.",
    )


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
    constraints: dict[str, Any] | None = Field(
        default=None,
        description="Verbatim from the package schema: enum, minimum, maximum, default, "
        "format, pattern, minLength/maxLength, minItems/maxItems (null when none).",
    )
    model_id: str | None = Field(
        default=None,
        description="The model document the field's type is ($ref to a package model), "
        "e.g. model:orderlineitem; null when none.",
    )


class ConflictStatementOut(Schema):
    where: str = Field(description='"description", "param:<name>" or "page:<url>".')
    quote: str
    source_url: str | None = None
    is_example: bool = False


class DocConflict(Schema):
    limit: str
    text: str = Field(description='"The docs state different values for <limit>:" + quotes.')
    statements: list[ConflictStatementOut]


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
    real_path: str | None = Field(default=None, description=_REAL_PATH)
    version_fixed: bool = Field(
        default=False, description="The package fixes this operation's API version."
    )
    rate_limit: dict[str, Any] | None = Field(
        default=None,
        description="Verbatim: {bucket, cost, group: {scope, group, limit, windowSeconds, "
        "algorithm, notes} | null} from request.json rateLimitCost and app.json rateLimits.",
    )
    deprecated: bool
    complete: bool
    source_url: str | None
    anchor: str | None
    text: str
    fields: list[FieldOut]
    scopes: list[str]
    required_scopes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Endpoint: requiredScopes [{authId, scopes}] verbatim (authId null when "
        "the package does not name the scheme).",
    )
    guides: list[str] = Field(
        default_factory=list,
        description="Endpoint: the knowledge units that name it (endpointId/endpointIds).",
    )
    conflicts: list[DocConflict] = Field(
        default_factory=list,
        description="x-kariz-conflicts: the docs state different values for a limit; every "
        "statement with its place, examples marked. Plume never picks one.",
    )
    linked_endpoints: list[str] = Field(
        default_factory=list,
        description="Knowledge unit: its endpoints (its own endpointId/endpointIds, then the "
        "page/slug links of knowledge-export/unit-links.json).",
    )
    endpoint_links: list[EndpointLink] = Field(
        default_factory=list,
        description="Knowledge unit: linkedEndpoints with the basis of each link.",
    )
    rule_sources: list[RuleSource] = Field(
        default_factory=list,
        description="Rules in this text stated on several documentation pages, each with every "
        "page as a citation (sourceUrl first). Empty when each rule names one page.",
    )
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
    eval: dict[str, Any] | None = Field(
        default=None,
        description="A succeeded job's model scored against its model gold (as POST "
        "/v1/models/{id}/eval); null when no gold covers its concept.",
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
    endpoints: list[str] = Field(
        default_factory=list,
        description="Endpoint document ids whose requiredScopes name this scope (this scheme).",
    )


class AuthSchemeSummary(Schema):
    id: str
    doc_id: str
    name: str
    type: str | None = Field(description="authorizationType from the package, verbatim.")
    grant_type: str | None
    header_name: str | None
    header_prefix: str | None = Field(default=None, description='Raw, e.g. "Bearer".')
    header_format: str | None = Field(
        default=None, description='How to send it: "Authorization: Bearer <token>".'
    )
    header_source: str | None = Field(
        default=None,
        description='"vendor" (the vendor states it: header_evidence) or "standard:rfc6750" '
        "(the OAuth 2.0 standard, not the vendor's text); null: unknown.",
    )
    header_evidence: str | None = Field(
        default=None, description="The vendor's quote (only when header_source is vendor)."
    )
    header_note: str | None = Field(
        default=None, description="Label to show when the header is the standard's."
    )
    query_param: str | None
    scopes: int
    variables: int


class AuthList(Schema):
    api: str
    build: str
    present: bool
    note: str | None
    schemes: list[AuthSchemeSummary]
    notices: list[Notice] = Field(
        default_factory=list, description="User-facing notices about auth (package warnings)."
    )


class AuthSchemeDetail(Schema):
    api: str
    build: str
    id: str
    doc_id: str
    name: str
    type: str | None
    grant_type: str | None
    header_name: str | None
    header_prefix: str | None = None
    header_format: str | None = Field(
        default=None, description='How to send it: "Authorization: Bearer <token>".'
    )
    header_source: str | None = Field(
        default=None, description='"vendor" | "standard:rfc6750" | null (unknown).'
    )
    header_evidence: str | None = Field(
        default=None, description="The vendor's quote (only when header_source is vendor)."
    )
    header_note: str | None = Field(
        default=None, description="Label to show when the header is the standard's."
    )
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
    notices: list[Notice] = Field(
        default_factory=list,
        description="User-facing notices about auth (package warnings), as on the auth list.",
    )


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


class ModelRef(Schema):
    doc_id: str
    title: str | None


class TriggerPayload(Schema):
    schema_ref: str | None = Field(description="The event's payloadSchemaRef, verbatim.")
    sample_ref: str | None = Field(description="The event's sampleRef, verbatim.")
    model: ModelRef | None = Field(
        description="The connector model the payload ref names (then `schema` is null and "
        "`fields` empty: read the model)."
    )
    payload_schema: dict[str, Any] | None = Field(
        alias="schema",
        serialization_alias="schema",
        description="The payload JSON schema, verbatim (null when unresolved or a model).",
    )
    sample: Any = Field(description="The payload sample, verbatim (null when none).")
    fields: list[FieldOut] = Field(
        description="The payload schema's fields as dotted paths, like a model's fields."
    )


class TriggerDetail(TriggerSummary):
    api: str
    build: str
    source_url: str | None
    event: dict[str, Any] = Field(description="The event JSON from the package, verbatim.")
    payload: TriggerPayload | None = Field(
        default=None,
        description="payloadSchemaRef / sampleRef read (null when the event states neither).",
    )


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
    notices: list[Notice] = Field(
        default_factory=list,
        description="User-facing notices about environments (package warnings).",
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


class ReportNoteOut(Schema):
    id: str
    kind: str = Field(description="note | duplicate (a near-duplicate report merged in)")
    text: str
    created_at: str
    client_name: str | None = None
    session_hash: str | None = None
    build: str | None = None
    redactions: int = 0


class ReportOut(Schema):
    id: str
    api: str
    build: str | None = None
    question: str = Field(description="As reported, redacted.")
    what_was_tried: str | None = None
    what_was_missing: str | None = None
    status: Literal["open", "answered", "search-miss", "package-gap", "out-of-scope"]
    reason: str | None = None
    report_count: int
    note_count: int
    created_at: str
    updated_at: str
    client_name: str | None = None
    session_hash: str | None = Field(default=None, description="Keyed hash of the MCP session.")
    redactions: int = 0
    notes: list[ReportNoteOut] | None = None


class ReportList(Schema):
    reports: list[ReportOut]
    enabled: bool = Field(
        description="Whether readers can report questions on this server (PLUME_REPORTS). The "
        "list and the status updates work either way."
    )


class ReportStatusUpdate(Schema):
    status: Literal["open", "answered", "search-miss", "package-gap", "out-of-scope"]
    reason: str | None = Field(default=None, max_length=1000)
