/**
 * Hand-written types for the Plume HTTP API (W1 stub).
 * Replaced by types generated from the backend OpenAPI once plume-6f publishes it (P3).
 */
/** The server sends ready | unpublished (recallAt5 is null until the eval gate has run). `updating` is mock-only. */
export type ApiStatus =
  | { kind: 'ready'; recallAt5: number | null }
  | { kind: 'unpublished'; recallAt5?: number | null }
  | { kind: 'updating'; progress: number };

/** Where an API's display name comes from: a maintainer's override, the package's own title, or derived from the id. */
export type NameSource = 'override' | 'package' | 'derived';

/** PUT /v1/apis/{api}/display: the resolved name, where it comes from, and what clearing the override gives back. */
export interface ApiDisplayName {
  api: string;
  name: string;
  nameSource: NameSource;
  packageName: string;
}

export interface ApiSummary {
  id: string;
  name: string;
  /** Where `name` comes from (absent on an older server). */
  nameSource?: NameSource;
  /** The producer's category key, e.g. "e-commerce"; "other" when missing. Use categoryLabel() to show it. */
  category: string;
  summary: string;
  endpoints: number;
  /** Model documents. Big APIs repeat the same schema many times: prefer modelNames to show a count. */
  models: number;
  /** Distinct model names (bundle roots excluded). */
  modelNames?: number;
  /** Distinct model structures (the same schema counts once). */
  modelShapes?: number;
  guides: number;
  docsAsOf: string | null; // ISO date; null while unpublished
  status: ApiStatus;
  logo: { text: string; color: string; url?: string | null };
  /**
   * What the latest build's notes say users can see: counts of confirmed and likely changes (wording-only ones
   * counted apart). Absent or null when the build has no notes or no visible non-wording change.
   */
  docsUpdated?: DocsUpdated | null;
}

export interface DocsUpdated {
  build: string;
  at: string;
  confirmed: number;
  likely: number;
  breaking: number;
  /** Wording-only changes are not in the counts above and never raise the badge. */
  wordingOnly?: number;
}

export interface ApiList {
  items: ApiSummary[];
}

export interface DraftIssue {
  code: string;
  field: string;
  api: string | null;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  /** The server's error code, e.g. "invalid_state", "gate_failed", "draft_refused". */
  readonly code?: string;
  /** Present on a refused model draft (422 draft_refused). */
  readonly issues?: DraftIssue[];
  /** Present on 409 api_in_use: the models and sets that pin the API. */
  readonly pinnedBy?: PinnedBy[];
  constructor(
    status: number,
    message: string,
    extra: { code?: string; issues?: DraftIssue[]; pinnedBy?: PinnedBy[] } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = extra.code;
    this.issues = extra.issues;
    this.pinnedBy = extra.pinnedBy;
  }
}

export type ItemKind = 'endpoint' | 'model' | 'guide' | 'auth' | 'trigger' | 'app';
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

/** Where a package's docs came from (public: url is always http(s); kind is one of docs|spec|changelog|sdk|other). */
export interface ApiSource {
  url: string;
  kind: string;
  fetchedAt?: string | null;
  /** How it was found ("entry", "given", "discovered from ..."): maintainer views carry it, the public API may not. */
  role?: string | null;
}

export interface ApiDetail extends ApiSummary {
  /** null: the build has no recorded package metadata (older builds); []: metadata but no http(s) source. */
  sources?: ApiSource[] | null;
  /** When the package was extracted (ISO); null for older builds. */
  extractedAt?: string | null;
  /** The package's rate-limit description, verbatim ([] when it has none; absent on an older server). */
  rateLimits?: ApiRateLimit[];
  chunks: number;
  isLive: boolean;
  tag: string | null; // e.g. "latest"; null while unpublished
  tags: string[];
  versions: string[];
  docLink: string | null;
  /** null until the eval gate has run (P4). */
  quality: {
    recallAt5: number;
    mrr: number;
    /** null: not measured by the server yet (needs a Claude-driven run). */
    inventedEndpoints: number | null;
    goldQuestions: number;
    evaluatedAt: string; // ISO date
    citationHitRate?: number;
    factAccuracy?: number;
    /** Gold questions whose expected document was not found. */
    missingExpected?: number;
    gatePassed?: boolean;
    /** The same scores per question source the gold set has; one "docs" row when it has no sources. Absent on older servers. */
    bySource?: SourceQuality[];
  } | null;
  /** All the warnings of the package's manifest (the server sends them to everyone; the page shows them to maintainers). */
  packageWarnings?: PackageWarning[];
  /** Notices for the sections of the API; the auth and environments sections show their own. */
  notices?: Notice[];
  index: {
    embedding: string | null;
    dimensions: number | null;
    store: string;
    build: string | null;
  };
  connect: { claudeCode: string; mcpUrl?: string };
  /** How many auth schemes, trigger events and webhook endpoints the package has (shows or hides the sections). */
  sections?: { auth: number; triggers: number; webhookEndpoints: number } | null;
}

export interface BrowseItem {
  id: string;
  kind: ItemKind;
  tags?: string[];
  title: string;
  method?: HttpMethod;
  path?: string;
  /** The path as the vendor serves it (with the version filled in), when the package says so; else null. */
  realPath?: string | null;
  resource?: string | null;
  deprecated?: boolean;
}

export interface BrowseResult {
  build?: string;
  items: BrowseItem[];
  total: number; // total items of this kind for the API
}

export type SearchMode = 'hybrid' | 'dense' | 'text';
export type KindFilter = 'all' | ItemKind;

export interface SearchRequest {
  query: string;
  mode: SearchMode;
  kind: KindFilter;
  topK: number;
}

export interface SearchHit {
  id: string;
  kind: ItemKind;
  title: string;
  subtitle: string; // e.g. "guide · shared" or "GET /admin/api/latest/orders.json"
  snippet: string;
  sourceUrl?: string | null;
  denseRank: number | null;
  textRank: number | null;
  denseScore: number; // 0..1, for the bar
  textScore: number; // 0..1
  fused: number;
}

export interface TraceStep {
  source: 'gemini' | 'embedder' | 'postgres' | 'plume';
  label: string;
  ms: number;
}

export interface SearchResponse {
  api: string;
  build?: string;
  docsAsOf: string;
  results: SearchHit[];
  trace: TraceStep[];
  totalMs: number;
  /** The JSON Claude receives from the reader tool, pretty-printed by the server. */
  claudePayload: string;
}

export interface AskResponse {
  api: string;
  build?: string;
  docsAsOf: string;
  question: string;
  /** Retrieval only: Plume returns the passages Claude would write the answer from. */
  passages: { id: string; title: string; quote: string; sourceUrl: string | null }[];
  trace: TraceStep[];
  totalMs: number;
}

export interface CheckCallRequest {
  method: HttpMethod;
  path: string;
  params: string[];
}

export interface CheckCallResponse {
  api: string;
  build: string;
  verdict: 'documented' | 'not_documented';
  /** false when the schema is flagged partial: absence is then not proven */
  complete: boolean;
  matched: { id: string; method: HttpMethod; path: string; realPath?: string | null } | null;
  evidence?: {
    docId: string;
    sourceUrl: string | null;
    anchor: string | null;
    quote: string | null;
  } | null;
  paramChecks: { name: string; found: boolean; where: string | null }[];
  checked: { endpoints: number; models: number };
  /** The other operation ids at the same METHOD + path (e.g. a package with three GET /{file_path} downloads). */
  alternatives?: string[];
}

// ---- maintainer: packages, jobs, build events (W3) ----

export interface MaintainerIdentity {
  name: string;
  /** Whether the server can generate models itself (a model key is configured). Absent on older servers. */
  generation?: boolean;
}

export interface ValidationCheck {
  key: string;
  title: string;
  detail: string;
  status: 'ok' | 'warn' | 'fail';
}

export interface PackageInfo {
  filename: string;
  sizeBytes: number;
  files: number;
  contents: { endpoints: number; models: number; guides: number };
  validation: ValidationCheck[];
  suggested: { apiId: string; displayName: string; tag: string };
}

export interface DiffItem {
  change: 'new' | 'changed' | 'removed';
  kind: ItemKind;
  title: string;
  method?: HttpMethod | null;
  path?: string | null;
  /** The server sends the chunk id here; mocks send a sentence. Shown as small text. */
  note: string;
}

export interface JobDiff {
  since: string;
  counts: { new: number; changed: number; removed: number; unchanged: number };
  items: DiffItem[];
  totalItems: number;
}

export interface EmbeddingPlan {
  toEmbed: number;
  total: number;
  model: string;
  dimensions: number;
  estimatedTokens: string;
  estimatedCost: string;
}

export interface EvalMetric {
  key: string;
  label: string;
  live: string;
  staged: string;
  delta: string;
  tone: 'ok' | 'neutral' | 'bad';
}

export interface JobEval {
  gate: { passed: boolean; message: string };
  metrics: EvalMetric[];
  release: { version: string; knowledgeFile: string; notes: string };
}

export type JobStatus =
  'uploaded' | 'reviewed' | 'building' | 'staged' | 'failed' | 'published' | 'discarded';

export interface Job {
  id: string;
  apiId: string;
  displayName: string;
  status: JobStatus;
  /** The tag the review diffed against (e.g. "latest"). */
  tag?: string;
  /** Set when status is failed. */
  error?: string | null;
  liveBuild: string | null;
  /** null until the build is staged. */
  stagedBuild: string | null;
  package: PackageInfo;
  diff: JobDiff | null;
  plan: EmbeddingPlan | null;
  eval: JobEval | null;
}

export interface ReviewRequest {
  apiId: string;
  displayName: string;
  tag: string;
}

export const STEP_KEYS = ['validate', 'chunk', 'diff', 'embed', 'store', 'evaluate'] as const;
export type StepKey = (typeof STEP_KEYS)[number];
export type StepStatus = 'pending' | 'running' | 'done' | 'failed';
export type EventSource = 'plume' | 'postgres' | 'gemini';

/** One build event from GET /v1/jobs/{id}/events (SSE). `id` is the SSE id, used to resume. */
export type JobEvent =
  /** `t` is an ISO time from the server (mocks send HH:MM:SS); show it with formatClock. */
  | { type: 'log'; id: string; t: string; source: EventSource; message: string }
  | { type: 'step'; id: string; key: StepKey; status: StepStatus; detail: string }
  | { type: 'progress'; id: string; done: number; total: number; etaSeconds: number | null }
  | { type: 'service'; id: string; service: 'postgres' | 'gemini'; detail: string }
  | { type: 'done'; id: string; status: 'staged' | 'failed'; message?: string };

// ---- canonical models (W4) ----

export interface ApiRef {
  id: string;
  /** The pinned build, when the server says which one it looked at. */
  build?: string | null;
  name: string;
  /** Short label for chips and avatars, e.g. "Shopify". */
  shortName: string;
  logo: { text: string; color: string; url?: string | null };
}

export type CoverageKind = 'direct' | 'derived' | 'absent';
export type Operation = 'read' | 'write';

/** What a package says about a concept in one API (all 0 where the API only has it derived or not at all). */
export interface ApiCounts {
  models: number;
  endpoints: number;
  operations: string[];
  fields: number;
}

export interface Concept {
  id: string;
  name: string;
  /** Why it is suggested: one paragraph written by the server from the packages. */
  reason: string;
  /** The server's per-API counts, shown next to the reason (nothing is shown that it does not send). */
  apiCounts?: Record<string, ApiCounts>;
  likelyFields: number;
  coverage: Record<string, CoverageKind>; // by api id
  operations: Operation[];
  difficulty: { tone: 'ok' | 'warn' | 'bad'; label: string };
  /** The documents behind the concept, per API (evidence the model is built from). */
  documents?: Record<string, string[]>;
}

/** multi = in 2+ of the selected APIs; single = in exactly one; all = both. */
export type SuggestScope = 'multi' | 'single' | 'all';

export interface SuggestQuery {
  q?: string;
  only?: SuggestScope;
  /** API ids (a subset of the selected ones): only concepts present, direct or derived, in every one of them. */
  require?: string[];
  inAll?: boolean;
  writeOnly?: boolean;
  limit?: number;
  offset?: number;
}

export interface SuggestResponse {
  apis: ApiRef[];
  concepts: Concept[];
  /** Concepts matching the filters (all pages). */
  total: number;
  limit: number;
  offset: number;
  nextOffset: number | null;
  /** Chip numbers: they follow q and require, not the scope or the chips themselves. */
  counts: { all: number; inAll: number; write: number; single: number };
  notModeled: { count: number; summary: string };
}

export interface GenerateRequest {
  apis: string[];
  concept: string;
  /** Maintainer token present: "server" is the default (a job); "claude" opens a session. */
  engine?: 'claude' | 'server';
}

export type FieldSupport = 'supported' | 'derived' | 'unsupported';

export interface FieldSource {
  paths: { path: string; type: string }[];
  /** Edge label for derived mappings, e.g. "not null = true" or "join: inventory_item_id". */
  transform?: string | null;
  fetch?: { endpoint: string } | null;
  join?: string[];
  /** `anchor` is "" when there is none; `docId` names the cited document. */
  evidence?: { quote: string; anchor: string; docId?: string }[];
}

export interface ModelField {
  name: string;
  /** The canonical path ("lines[].price.amount"); the name for a top-level field. */
  path?: string;
  /** The sub-fields of an object or array field (up to 3 levels). Absent on flat fields. */
  fields?: ModelField[];
  type: string;
  description?: string | null;
  required: boolean;
  support: Record<string, FieldSupport>; // by api id
  sources: Record<string, FieldSource>;
}

/** An API whose docs changed since a model was built: the build the model pinned and the current one. */
export interface StaleInput {
  api: string;
  pinned: string;
  current: string;
}

/** Who can see a model: official = released by a maintainer (public lists); unlisted = anyone with the link. */
export type ModelVisibility = 'official' | 'unreleased' | 'unlisted' | 'discarded' | 'superseded';

export interface ModelLineage {
  id: string;
  version: number;
  versions: number;
  /** The model this one was revised from; it can be in another lineage. */
  basedOn: string | null;
  latestId: string;
  history: { id: string; version: number; createdAt: string; visibility: ModelVisibility }[];
}

/** Something the server noticed about a mapping and did not refuse (e.g. WRITE_ONLY_SOURCE). */
export interface ModelWarning {
  code: string;
  /** The canonical field the warning is about, as in `fields[].path`. */
  field?: string | null;
  api?: string | null;
  message?: string | null;
}

/** An official model the one being released could replace (same concept), as the release dialog lists it. */
export interface Supersedable {
  id: string;
  /** The model's name (several share it): the dialog adds version, date and id. */
  name?: string;
  createdAt?: string;
  concept?: string;
  /** The API ids it covers. */
  apis: string[];
  stale?: boolean;
  version?: number;
  /** Its API set is inside the new model's: releasing the new one loses no API. */
  covered?: boolean;
}

export interface ModelSnapshot {
  id: string;
  name: string;
  visibility?: ModelVisibility;
  official?: boolean;
  origin?: 'user' | 'maintainer';
  /** "claude" or "gemini:<model>" */
  generator?: string;
  lineage?: ModelLineage;
  /** "/models/{id}": the web route of the model, the link is the id. */
  sharePath?: string;
  /** PLUME_WEB_PUBLIC_URL + sharePath, or null when the server does not know its public URL. */
  shareUrl?: string | null;
  /** The text of "Modify with Claude", built by the server (it names the tools). */
  revisePrompt?: string;
  /** The ids of the other official models of the same concept (case-insensitive) over the same APIs. */
  sameConcept?: string[];
  /** Warnings the server attached to the mappings (absent on older servers). */
  warnings?: ModelWarning[];
  /** The official models this one replaced when it was released. */
  supersedes?: string[];
  /** Set once a newer model replaced this one (visibility "superseded"): readable by id, out of the lists. */
  supersededBy?: string | null;
  supersededAt?: string | null;
  /** True when a pinned API has a newer build: the model is built on older docs. */
  stale?: boolean;
  staleInputs?: StaleInput[];
  impact?: Impact | null;
  concept?: string;
  sessionId?: string;
  description: string;
  status: 'generated_unverified';
  generatedAt: string;
  promptVersion: string;
  inputs: (ApiRef & { build: string })[];
  fields: ModelField[];
  /** Question text may contain **bold** spans. */
  openQuestions: { question: string; detail?: string | null; options?: string[] }[];
  coverage: Record<string, { mapped: number; total: number }>;
  citations: { checked: number; found: number; missing: string[] };
}

/** POST /v1/models/generate: the server runs no LLM, it opens a session for Claude (or a maintainer) to answer. */
export interface GenerateResponse {
  sessionId: string;
  /** ready: a snapshot already exists for the current builds; awaiting_draft: a draft is needed. */
  status: 'awaiting_draft' | 'ready';
  snapshotId: string | null;
  inputs: { api: string; build: string }[];
  contextUrl: string;
  claudePrompt: string;
  /** The public reader MCP. */
  mcpUrl: string;
  /** The maintainer MCP the prompt needs (bearer token). */
  maintainerMcpUrl?: string;
}

/** POST /v1/models/generate with the token (engine "server"): 202, the model is written on the server. */
export interface GenerateJobResponse {
  jobId: string;
  status: 'queued';
  eventsUrl: string;
}

export function isGenerateJob(r: GenerateResponse | GenerateJobResponse): r is GenerateJobResponse {
  return 'jobId' in r;
}

/** GET /v1/models/sessions/{sid}: a public poll for "has the model been stored yet?". */
export interface ModelSessionStatus {
  sessionId: string;
  status: 'open' | 'submitted';
  /** The latest draft accepted for this session. */
  snapshotId: string | null;
  visibility: ModelVisibility | null;
  apis: string[];
  concept: string;
  basedOn: string | null;
}

export interface ModelJob {
  jobId: string;
  /** "model_set" for a set; absent or "model" for a single model. */
  kind?: 'model' | 'model_set';
  setId?: string | null;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  apis: string[];
  concept: string;
  round: number;
  maxRounds: number;
  snapshotId: string | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

/** The events of a server-side generation (the SSE `event:` name is the type). */
export type ModelJobEvent =
  | { type: 'queued'; id?: string; jobId: string }
  | { type: 'started'; id?: string; apis: string[]; concept: string }
  | { type: 'context'; id?: string; documents: number; fields: number }
  | { type: 'round'; id?: string; n: number; of: number }
  | { type: 'refused'; id?: string; round: number; issues: DraftIssue[] }
  | { type: 'accepted'; id?: string; snapshotId?: string; setId?: string }
  /** While a model call is in flight: how long the job has run and what it is waiting for. */
  | {
      type: 'heartbeat';
      id?: string;
      /** Seconds since the job was created. */
      elapsed: number;
      round?: number;
      of?: number;
      phase?: string;
      detail?: string;
      /** For a set job: the member being written. */
      concept?: string;
    }
  /** A draft was accepted with warnings and sent back once for repair. */
  | { type: 'warnings'; id?: string; round: number; warnings: ModelWarning[] }
  /** A model set job: one member model was written and accepted (its own rounds ran before). */
  | { type: 'member'; id?: string; concept: string; snapshotId: string; round?: number }
  /** A model set job: the relations proposed from the documented candidates (all undecided). */
  | { type: 'proposals'; id?: string; relations: string[]; openQuestions: number }
  | { type: 'failed'; id?: string; code: string; message: string }
  | {
      type: 'done';
      id?: string;
      status: ModelJob['status'];
      snapshotId: string | null;
      setId?: string | null;
    };

/**
 * In a My models list: a link lists the version saved INTO it. When the lineage has a newer version elsewhere (someone
 * with the model's link saved one) this says which; `url` is the server's own address for it (the web links by id).
 */
export interface NewerVersion {
  id: string;
  version: number;
  url?: string;
}

/**
 * How newer docs touch a model or set (server-side: it knows which document fields a mapping cites). `unknown` means a
 * pinned build or one in between has no notes: never say "unaffected" then. Absent: the server does not say (an older
 * server): the UI falls back to the stale mark.
 */
export type ImpactStatus = 'current' | 'updated_unaffected' | 'affected' | 'unknown';

export interface Impact {
  status: ImpactStatus;
  affectedCount: number;
  breakingCount: number;
  /** A set: its status per member (the set's is the worst of them). */
  byMember?: { concept: string; modelId?: string; status: ImpactStatus; affectedCount: number }[];
}

/** GET /v1/models/{id}/impact: which mappings a visible change touches. */
export interface ModelImpact {
  status: ImpactStatus;
  affectedCount: number;
  breakingCount: number;
  pinned?: Record<string, string>;
  latest?: Record<string, string | null>;
  /** The mappings a visible change touches (`member`: the set member, on a set's). */
  affected: { field: string; api: string; member?: string | null; change: PublicChange }[];
  byMember?: { concept: string; modelId?: string; status: ImpactStatus; affectedCount: number }[];
}

export interface ModelListItem {
  id: string;
  name: string;
  concept: string;
  apis: string[];
  generatedAt: string;
  /** Released (official) models only, in the public list. */
  official?: boolean;
  visibility?: ModelVisibility;
  version?: number;
  versions?: number;
  stale?: boolean;
  staleInputs?: StaleInput[];
  impact?: Impact | null;
  /** Only in a My models list: a newer version of this lineage exists elsewhere (null/absent: this is the latest). */
  newerVersion?: NewerVersion | null;
}

/** GET /v1/models/sessions/{id}/context: a compact index of the evidence (field lists are paged separately). */
export interface ModelContext {
  session_id: string;
  concept: string;
  apis: {
    api: string;
    build: string;
    documents: {
      doc_id: string;
      kind: string;
      title: string;
      endpoint: string | null;
      /** A count; the fields themselves come from the evidence route. */
      fields: number;
      complete: boolean;
    }[];
  }[];
  next?: string;
  instructions?: string;
  draft_format?: unknown;
  status?: string;
}

/** GET /v1/models/sessions/{id}/evidence?api=&doc=&cursor=: one page of fields (about 20k characters at most). */
export interface EvidencePage {
  session_id: string;
  api: string;
  build: string;
  documents: {
    doc_id: string;
    title: string;
    endpoint: string | null;
    source_url: string | null;
    complete: boolean;
    fields: {
      path: string;
      type: string | null;
      location: string;
      required: boolean;
      description: string | null;
    }[];
  }[];
  returned: number;
  total_fields: number;
  next_cursor: number | null;
  missing_doc_ids: string[];
}

/** Scores over the gold questions of one source ("docs" or "spec"). */
export interface SourceQuality {
  source: string;
  recallAt5: number;
  mrr: number;
  /** Top-1: the first result is an expected one. */
  citationHitRate: number;
  /** Search questions of this source. */
  questions: number;
}

/** GET /v1/apis/{api}/documents/{docId}: one stored document (what a citation points at). */
export interface DocumentOut {
  api: string;
  build: string;
  docsAsOf: string;
  id: string;
  kind: string;
  title: string;
  resource: string | null;
  method: string | null;
  path: string | null;
  /** The path as the vendor serves it (e.g. "/wp-json/wc/v3/orders"); null when the package does not say. */
  realPath?: string | null;
  /** True when the version in realPath is fixed by the package, not a variable. */
  versionFixed?: boolean;
  /** The limit that applies to this endpoint: its bucket, its cost and the group it counts in. */
  rateLimit?: EndpointRateLimit | null;
  deprecated: boolean;
  complete: boolean;
  sourceUrl: string | null;
  anchor: string | null;
  /** Plain text taken from the vendor docs: untrusted, render as text. */
  text: string;
  /** Section tags from the package (e.g. "webhooks"); added with the package sections. */
  tags?: string[];
  /** The package's source JSON, verbatim (untrusted): request.json, the model schema, the scheme or event JSON. */
  raw?: unknown;
  /** True when `raw` was cut to the server's size cap. */
  rawTruncated?: boolean;
  /** Structured status codes, when the package has them. */
  responses?: Record<string, unknown>[];
  /** Documented errors, verbatim from the package (e.g. {status, meaning, retryable}); [] when none. */
  errors?: Record<string, unknown>[];
  fields: {
    name: string;
    location: string;
    type: string | null;
    required: boolean;
    description: string | null;
    /** What the package says about the allowed values; null when nothing. */
    constraints?: FieldConstraints | null;
  }[];
  scopes: string[];
  /** Endpoint: the scopes it needs per auth scheme (authId null = the package names no scheme). Absent on older servers. */
  requiredScopes?: RequiredScopes[];
  /** Endpoint: the knowledge units (guides) that name it, as document ids. */
  guides?: string[];
  /** Guide: the endpoints it is about, as document ids. */
  linkedEndpoints?: string[];
  /** Guide: the same endpoints with why each is linked (text | page | slug); absent on older servers. */
  endpointLinks?: EndpointLinkOut[];
}

/** One endpoint a guide is linked to, and the basis of the link. */
export interface EndpointLinkOut {
  endpointId: string;
  /** "text": the guide names the endpoint; "page": same docs page; "slug": matching names. Others are shown as sent. */
  linkBasis: string;
}

/** The scopes an endpoint needs under one auth scheme, verbatim from the package. */
export interface RequiredScopes {
  authId: string | null;
  scopes: string[];
}

/** The allowed values of a field, verbatim from the package (untrusted: show as text). */
export interface FieldConstraints {
  enum?: unknown[];
  minimum?: unknown;
  maximum?: unknown;
  exclusiveMinimum?: unknown;
  exclusiveMaximum?: unknown;
  minLength?: unknown;
  maxLength?: unknown;
  minItems?: unknown;
  maxItems?: unknown;
  default?: unknown;
  format?: unknown;
  pattern?: unknown;
}

/** One rate-limit group of a package, verbatim; the fields a package leaves out are absent. */
export interface RateLimitGroup {
  scope?: string | null;
  group?: string | null;
  limit?: number | string | null;
  windowSeconds?: number | string | null;
  algorithm?: string | null;
  notes?: string | null;
  [key: string]: unknown;
}

/** An entry of an API's rateLimits: a scope, an algorithm, the headers that report it, maybe one group's numbers. */
export interface ApiRateLimit extends RateLimitGroup {
  headerNames?: string[] | string | null;
}

export interface EndpointRateLimit {
  bucket?: string | null;
  cost?: number | string | null;
  group?: RateLimitGroup | null;
}

// ---- remove an API (maintainer) ----

/** A model or set that pins an API: removing the API retires it. */
export interface PinnedBy {
  type: 'model' | 'set';
  id: string;
  name: string;
  visibility: 'official' | 'unreleased';
}

export interface RemovalPreview {
  api: string;
  pinnedBy: PinnedBy[];
}

export interface RemoveApiRequest {
  /** Must equal the API id. */
  confirm: string;
  /** Remove although models or sets pin it (they are retired). */
  force?: boolean;
  reason?: string;
}

export interface RemoveApiResult {
  api: string;
  removed: Record<string, number | string | boolean>;
  retired: (PinnedBy & { now: 'superseded' | 'discarded' })[];
  forced: boolean;
}

// ---- package sections: auth, triggers, environments (from the package, nothing invented) ----

export interface AuthSchemeSummary {
  id: string;
  docId: string;
  name: string;
  type: string | null;
  grantType: string | null;
  headerName: string | null;
  queryParam: string | null;
  scopes: number;
  variables: number;
}

export interface AuthList {
  api: string;
  build: string;
  present: boolean;
  /** "not in this package" when absent. */
  note: string | null;
  schemes: AuthSchemeSummary[];
  /** What the package's warnings mean for this section; absent on older servers. */
  notices?: Notice[];
}

/** A user-facing note about a package (from its warnings), with the section it applies to. Untrusted text. */
export interface Notice {
  code: string;
  /** "auth" or "environments". */
  section: string;
  text: string;
}

/** One warning of the package's manifest.json, verbatim (maintainer view). */
export interface PackageWarning {
  code: string;
  text: string;
}

export interface AuthSchemeDetail {
  api: string;
  build: string;
  id: string;
  docId: string;
  name: string;
  type: string | null;
  grantType: string | null;
  headerName: string | null;
  queryParam: string | null;
  scopes: {
    scope: string | null;
    description: string | null;
    /** Endpoint document ids whose requiredScopes name this scope; absent on older servers. */
    endpoints?: string[];
  }[];
  variables: { name: string; description: string | null; type: string | null; required: boolean }[];
  /** Verbatim from the package: in Shopify a list of {order, text}; other shapes possible. */
  setupSteps: unknown[] | null;
  /** Verbatim object, e.g. {notes, refreshBehavior}. */
  tokenLifetime: Record<string, unknown> | null;
  testUrl: string | null;
  /** The auth JSON and its variables JSON Schema, verbatim (untrusted). */
  scheme: Record<string, unknown>;
  variablesSchema: Record<string, unknown> | null;
  file: string | null;
}

export interface TriggerSummary {
  /** e.g. "app/scopes_update" (contains "/": URL-encode it in a path). */
  key: string | null;
  docId: string;
  title: string;
  description: string | null;
  resource: string | null;
  delivery: string | null;
  /** Set when the event is delivered by polling this endpoint instead of a webhook. */
  syncEndpointId?: string | null;
}

export interface TriggerList {
  api: string;
  build: string;
  present: boolean;
  note: string | null;
  total: number;
  items: TriggerSummary[];
  /** The webhook delivery mechanism, verbatim from the package ([] when none). */
  webhooks?: Record<string, unknown>[];
  /** The stream endpoint ids mentioned by the mechanism and the events, resolved to a document; null = not in this build. */
  endpointRefs?: EndpointRefs;
}

export type EndpointRefs = Record<string, { docId: string; method: string; path: string } | null>;

export interface TriggerDetail extends TriggerSummary {
  api: string;
  build: string;
  sourceUrl: string | null;
  /** The event JSON, verbatim (untrusted). */
  event: Record<string, unknown>;
  /** What the event carries; null (or absent on older servers) when the event states no payload. */
  payload?: TriggerPayload | null;
}

/** The payload an event states (payloadSchemaRef / sampleRef), read by the server. All text is untrusted. */
export interface TriggerPayload {
  /** The event's refs, verbatim. */
  schemaRef: string | null;
  sampleRef: string | null;
  /** The payload JSON schema, verbatim; null when unresolved or when the ref names a model. */
  schema: Record<string, unknown> | null;
  /** The payload sample, verbatim; null when none. */
  sample: unknown;
  /** The connector model the ref names; then `schema` is null and `fields` empty. */
  model: { docId: string; title: string | null } | null;
  /** The schema's fields as dotted paths (line_items[].sku), like a model's. */
  fields: DocumentOut['fields'];
}

export interface Environment {
  key?: string;
  kind?: string;
  name?: string;
  baseUrl?: string;
  servers?: Record<string, string>;
  isDefault?: boolean;
  [more: string]: unknown;
}

export interface EnvironmentsOut {
  api: string;
  build: string;
  present: boolean;
  note: string | null;
  environments: Environment[];
  versioning: { format?: string; scheme?: string; current?: string; versions?: string[] } | null;
  baseUrls: string[] | null;
  variablesSchema: Record<string, unknown> | null;
  notices?: Notice[];
}

/** GET /v1/apis/{api}/mcp: only when the vendor runs an MCP server. Docs-only packages have none (present=false). */
export interface McpOut {
  api: string;
  build: string;
  present: boolean;
  note: string | null;
  servers: {
    id: string;
    /** The server JSON, verbatim (untrusted). */
    server: Record<string, unknown>;
    tools: { tool: string; inputSchema: unknown; outputSchema: unknown | null }[];
  }[];
}

// ---- model sets: several canonical models and the relations between them ----

export type RelationKind = 'embedded' | 'reference';
export type Cardinality = '1:1' | '1:n' | 'n:1' | 'n:m';
/** How an API documents the relation: nested objects, a sub-resource path, an id field, a model reference. */
export type RelationSupport = 'nested' | 'sub_resource' | 'id_field' | 'model_ref';

export interface RelationSource {
  as?: string;
  paths: string[];
  /** The endpoint to fetch the related thing from: a string, or an object with the endpoint. */
  fetch?: string | { endpoint: string } | null;
  evidence?: { docId?: string; quote: string; anchor?: string }[];
}

/** One way the relation could be designed, and whether it can be chosen without new field mappings. */
export interface RelationOption {
  kind: RelationKind;
  from: string;
  to: string;
  cardinality: Cardinality;
  embed: { field: string } | null;
  ref: { field: string; key: string } | null;
  editable: boolean;
  /** What is missing when it is not editable ("Product: a field holding the Order id"): revise with Claude. */
  missing: string[];
  current: boolean;
}

export interface SetRelation {
  id: string;
  from: string;
  to: string;
  kind: RelationKind;
  cardinality: Cardinality;
  embed: { field: string } | null;
  ref: { field: string; key: string } | null;
  /** false = undecided: a proposal to be confirmed. */
  confirmed: boolean;
  candidate?: boolean;
  support: Record<string, RelationSupport | null>;
  sources: Record<string, RelationSource>;
  editableOptions?: RelationOption[];
}

export interface SetMember {
  concept: string;
  modelId: string;
  name?: string;
  /** Leaves. */
  fieldCount?: number;
  coverage?: Record<string, { mapped: number; total: number }>;
  visibility?: ModelVisibility;
  version?: number;
  /** The member model is not available (not released, or not visible to this reader). */
  missing?: boolean;
}

export interface ModelSet {
  kind: 'model_set';
  id: string;
  name: string;
  description?: string | null;
  visibility: ModelVisibility;
  official: boolean;
  origin?: 'user' | 'maintainer';
  generator?: string;
  generatedAt: string;
  releasedAt?: string | null;
  basedOn?: string | null;
  inputs: ApiRef[];
  stale?: boolean;
  staleInputs?: StaleInput[];
  impact?: Impact | null;
  members: SetMember[];
  relations: SetRelation[];
  /** Ids of the relations still to decide. */
  undecided: string[];
  aliases?: { names: Record<string, string>; concept: string }[];
  openQuestions: { question: string; detail?: string | null; options?: string[] }[];
  lineage?: ModelLineage;
  sharePath?: string;
  shareUrl?: string | null;
  revisePrompt?: string;
}

export interface SetListItem {
  id: string;
  name: string;
  apis: string[];
  members: string[];
  relations: number;
  undecided: number;
  generatedAt: string;
  visibility?: ModelVisibility;
  official?: boolean;
  version?: number;
  versions?: number;
  stale?: boolean;
  impact?: Impact | null;
  /** Only in a My models list: a newer version of this lineage exists elsewhere (null/absent: this is the latest). */
  newerVersion?: NewerVersion | null;
}

/** The design fields of a relation the editor may change (anything else is refused with 400). */
export interface RelationEdit {
  id: string;
  kind?: RelationKind;
  cardinality?: Cardinality;
  embed?: { field: string } | null;
  ref?: { field: string; key: string } | null;
  from?: string;
  to?: string;
  confirmed?: boolean;
}

// ---- "My models": a link per person (collections replace owner keys) ----

/** What a save without a maintainer token answers instead of an owner key: the link of the person's collection. */
export interface CollectionRef {
  id: string;
  /** "<web address>/mine/<id>", or just "/mine/<id>" when the server does not know the web's address. */
  url: string;
  /** True when the save started a new collection (none was sent, or the one sent is unknown: see `note`). */
  created: boolean;
  note?: string | null;
}

/** GET /v1/collections/{id}: the latest non-discarded version of each model and set in it, newest first. */
export interface Collection {
  id: string;
  url: string;
  /** Set when this link was merged into another: it then lists nothing. */
  mergedInto: string | null;
  count: number;
  models: ModelListItem[];
  sets: SetListItem[];
}

// ---- related concepts (POST /v1/models/suggest-related) and creating a set ----

/** One place in an API's docs that connects two concepts. Deterministic: no LLM. */
export interface RelatedEvidence {
  kind: RelationSupport;
  docId?: string | null;
  quote: string;
  paths: string[];
  fetch?: string | null;
  many?: boolean;
}

export interface RelatedCandidate {
  id: string;
  parent: { id: string; name: string };
  child: { id: string; name: string };
  /** The designs the evidence supports. */
  options: { kind: 'embedded' | 'reference'; cardinality: RelationOption['cardinality'] }[];
  /** Per API id: where its docs show it. */
  sources: Record<string, RelatedEvidence[]>;
}

export interface RelatedConcept {
  id: string;
  name: string;
  /** Per API id: how the docs connect it (nested, sub_resource, id_field, model_ref). */
  kinds: Record<string, RelationSupport[]>;
  candidates: RelatedCandidate[];
}

/** Different names at the same documented position (variant / variation): only the user may call them one. */
export interface RelatedAlias {
  parent: { id: string; name: string };
  names: Record<string, { id: string; name: string }>;
  evidence: Record<string, RelatedEvidence>;
  note: string;
}

export interface RelatedConcepts {
  apis: ApiRef[];
  concept: { id: string; name: string };
  related: RelatedConcept[];
  total: number;
  limit: number;
  offset: number;
  nextOffset: number | null;
  aliases: RelatedAlias[];
}

/** Concepts the user decided are one thing: `names` is the name each API uses for `concept`. */
export interface SetAlias {
  concept: string;
  names: Record<string, string>;
}

export interface SetSessionRequest {
  apis: string[];
  concepts: string[];
  aliases?: SetAlias[];
}

/** POST /v1/model-sets/sessions: one model session per member, for Claude to fill. */
export interface SetSessionResponse {
  setSessionId: string;
  inputs: { api: string; build: string }[];
  memberSessions: Record<string, string>;
  contextUrl: string;
  claudePrompt: string;
}

/** GET /v1/model-sets/sessions/{id}: has the set been stored yet? (the server sends snake_case) */
export interface SetSessionStatus {
  setSessionId: string;
  status: 'open' | 'submitted';
  setId: string | null;
  visibility: ModelVisibility | null;
  concepts: string[];
}

// ---- release notes: what changed between builds, and the maintainer's review after a publish ----

/** Where a change comes from: the vendor docs (confirmed, likely) or the extractor (suspect, unknown). */
export type ChangeClass = 'confirmed' | 'likely' | 'suspect' | 'unknown';
/** After a publish nothing is held; the maintainer keeps the build or rolls it back. */
export type ReleaseReview = 'pending' | 'kept' | 'rolled_back';

export interface ChangeSubject {
  docId?: string | null;
  method?: string | null;
  path?: string | null;
  model?: string | null;
  fieldPath?: string | null;
  location?: string | null;
}

/** One side of a change: values, and a short quote from the vendor docs of THAT build (plain text). */
export interface ChangeValue {
  type?: string | null;
  required?: boolean | null;
  quote?: string | null;
}

export interface ChangeItem {
  id: string;
  kind: string;
  op: string;
  subject: ChangeSubject;
  before?: ChangeValue | null;
  after?: ChangeValue | null;
  breaking: boolean;
  breakingReason?: string | null;
  class: ChangeClass;
  evidence?: {
    sourceUrl?: string | null;
    anchor?: string | null;
    quote?: string | null;
    pageHashBefore?: string | null;
    pageHashAfter?: string | null;
    changelog?: string | null;
    /** Urls the change is attributed to (empty when not attributed). */
    sources?: string[] | null;
    sourceKind?: 'spec' | 'docs' | 'changelog' | 'sdk' | 'other' | 'mixed' | null;
    attribution?: 'recorded' | 'not-recorded' | null;
  } | null;
  artifactRules?: string[];
  wordingOnly?: boolean;
  from?: string;
  to?: string;
  toDocsAsOf?: string | null;
  /** False for suspect/unknown (and renames): never shown to users. */
  visibleToUsers?: boolean;
  /** The class the server computed: what a demote goes back to. */
  computedClass?: ChangeClass;
  promotedBy?: string | null;
  promotedAt?: string | null;
}

export interface ReleaseCounts {
  confirmed: number;
  likely: number;
  breaking: number;
  /** Maintainer only. */
  suspect?: number;
  unknown?: number;
  wordingOnly?: number;
  renamed?: number;
  total?: number;
  byKind?: Record<string, number>;
}

/** One build's notes on the timeline of an API (GET /v1/apis/{api}/release-notes, newest first; only builds WITH notes). */
export interface ReleaseSummary {
  from: string;
  /** The build the notes are about. */
  to: string;
  toDocsAsOf?: string | null;
  computedAt: string;
  review: ReleaseReview;
  needsAttention: boolean;
  attentionReason?: string | null;
  /** This build is `latest`. */
  tagged: boolean;
  counts: ReleaseCounts;
}

/** The suspect items of one artifact rule, with the server's own one-sentence explanation (the web holds no rule text). */
export interface ReportGroup {
  rule: string;
  title: string;
  explanation: string;
  /** How many changes the rule flagged; `items` holds only the first 50 (the rest: GET .../report/{rule}). */
  count?: number;
  items: ChangeItem[];
}

/** One page of a report group (GET .../release-notes/report/{rule}?cursor=&limit=). */
export interface ReportPage {
  rule: string;
  count: number;
  items: ChangeItem[];
  nextCursor: number | null;
}

export interface ReleaseDecision {
  by: string;
  at: string;
  decision: 'keep' | 'rollback' | 'rollforward' | 'promote' | 'demote';
  note?: string | null;
  reason?: string | null;
  item?: string | null;
  fromClass?: ChangeClass | null;
}

/** A source of a package as stream recorded it (maintainer view). */
export interface PackageSource extends ApiSource {
  contentSha256?: string | null;
  etag?: string | null;
  version?: string | null;
  /** "entry" or "discovered from <url>". */
  role?: string | null;
  /** True when the source is only the manifest's single source url (no sources[] recorded). */
  fallback?: boolean | null;
}

/** Stream found two sources disagreeing about a unit's field; it chose one. */
export interface SourceConflict {
  unit: string;
  field: string;
  values: { url: string; value: unknown }[];
  chosen?: unknown;
  reason?: string | null;
}

/** What produced a build's package (stream and its rules): the A and B sides of a diff. */
export interface BuildPackage {
  sources?: PackageSource[] | null;
  changelogUrls?: string[] | null;
  /** unit -> the urls it was built from. */
  unitSources?: Record<string, string[]> | null;
  conflicts?: SourceConflict[] | null;
  conflictsChecked?: string[] | null;
  conflictsUnchecked?: string[] | null;
  streamVersion?: string | null;
  rulesHash?: string | null;
  runId?: string | null;
  extractedAt?: string | null;
  /** Pages stream could not read, units it blocked, pages it saw change: lists or counts (the server may send either). */
  failedPages?: unknown;
  blockedUnits?: unknown;
  changedPages?: unknown;
  pageHashes?: unknown;
  /** True when this package has no page text to compare with (only the baseline). */
  baselineOnly?: boolean | null;
  llmFiles?: unknown;
}

/** GET /v1/apis/{api}/builds/{build}/release-notes (maintainer): every item, the extraction report and the review. */
export interface ReleaseNotes {
  /** Stream's source conflicts for the new build. Absent on notes computed before sources were recorded. */
  conflicts?: SourceConflict[] | null;
  /** notCompared: units stream did NOT compare (never the same as "no conflicts"). */
  conflictCheck?: { checked: number; notCompared: number } | null;
  api?: string;
  to?: string;
  toDocsAsOf?: string | null;
  /** stream or its rules changed between the two builds: suspect changes are likelier. */
  extractorChanged?: boolean;
  review: ReleaseReview;
  needsAttention: boolean;
  attentionReason?: string | null;
  /** This build is `latest` now (only that one can be rolled back). */
  tagged: boolean;
  computedAt: string;
  decisions: ReleaseDecision[];
  counts: ReleaseCounts;
  report: ReportGroup[];
  /** EVERY item (those users see carry `visibleToUsers`); can be thousands for a big API. */
  items?: ChangeItem[];
  from?: string | null;
  package?: { from?: BuildPackage | null; to?: BuildPackage | null } | null;
  gold?: { before?: Record<string, number> | null; after?: Record<string, number> | null } | null;
}

/** POST .../release-notes/rollback: where `latest` points now. */
export interface RollbackResult {
  tag: string;
  buildId: string;
  previous: string;
  review: ReleaseReview;
}

// ---- public changes (release notes the users see) ----

/** One build of the public timeline (GET /v1/apis/{api}/changes/timeline): only builds that have notes, newest first. */
export interface PublicBuild {
  build: string;
  from?: string | null;
  docsAsOf?: string | null;
  /** This build is `latest`. */
  latest: boolean;
  counts: { confirmed: number; likely: number; breaking: number; wordingOnly: number };
}

/**
 * One change as users see it (GET /v1/apis/{api}/changes): only confirmed or likely, never an artifact rule, hash or
 * review. `quote` is plain text from the vendor docs; `vendorUrl` is http(s) or null; `anchor` has no "#".
 */
export interface PublicChange {
  id: string;
  from?: string;
  to?: string;
  toDocsAsOf?: string | null;
  kind: string;
  op: string;
  subject: ChangeSubject;
  before?: ChangeValue | null;
  after?: ChangeValue | null;
  breaking: boolean;
  breakingReason?: string | null;
  class: 'confirmed' | 'likely';
  /** True for a likely change: "per the vendor's changelog". */
  perVendorChangelog?: boolean;
  wordingOnly?: boolean;
  quote?: string | null;
  vendorUrl?: string | null;
  anchor?: string | null;
  sourceKind?: string | null;
  /** The API path of the document (the build it was found in): not a web address. */
  documentUrl?: string | null;
  /** A whole endpoint or model was removed: there is no document to open any more. */
  removedDocument?: boolean;
}

/** The counts of the selection after the filters but BEFORE the search and paging. */
export interface ChangeTotals {
  confirmed: number;
  likely: number;
  breaking: number;
  wordingOnly: number;
  byKind?: Record<string, number>;
}

export interface ChangesPage {
  api?: string;
  builds?: string[];
  computedAt?: string | null;
  totals: ChangeTotals;
  /** How many match the search (before paging). */
  matched?: number;
  items: PublicChange[];
  nextCursor: number | null;
}

export interface ChangesQuery {
  build?: string;
  since?: string;
  breaking?: boolean;
  /** One kind, or several as a comma list ("param,property"). */
  kind?: string;
  wordingOnly?: boolean;
  q?: string;
  cursor?: number | null;
  limit?: number;
}
