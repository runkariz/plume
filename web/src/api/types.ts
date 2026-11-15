/**
 * Hand-written types for the Plume HTTP API (W1 stub).
 * Replaced by types generated from the backend OpenAPI once plume-6f publishes it (P3).
 */
/** The server sends ready | unpublished (recallAt5 is null until the eval gate has run). `updating` is mock-only. */
export type ApiStatus =
  | { kind: 'ready'; recallAt5: number | null }
  | { kind: 'unpublished'; recallAt5?: number | null }
  | { kind: 'updating'; progress: number };

export interface ApiSummary {
  id: string;
  name: string;
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
  constructor(
    status: number,
    message: string,
    extra: { code?: string; issues?: DraftIssue[] } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = extra.code;
    this.issues = extra.issues;
  }
}

export type ItemKind = 'endpoint' | 'model' | 'guide' | 'auth' | 'trigger' | 'app';
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface ApiDetail extends ApiSummary {
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
  } | null;
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
  matched: { id: string; method: HttpMethod; path: string } | null;
  evidence?: {
    docId: string;
    sourceUrl: string | null;
    anchor: string | null;
    quote: string | null;
  } | null;
  paramChecks: { name: string; found: boolean; where: string | null }[];
  checked: { endpoints: number; models: number };
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
export type ModelVisibility = 'official' | 'unreleased' | 'unlisted' | 'discarded';

export interface ModelLineage {
  id: string;
  version: number;
  versions: number;
  /** The model this one was revised from; it can be in another lineage. */
  basedOn: string | null;
  latestId: string;
  history: { id: string; version: number; createdAt: string; visibility: ModelVisibility }[];
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
  /** True when a pinned API has a newer build: the model is built on older docs. */
  stale?: boolean;
  staleInputs?: StaleInput[];
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
  | { type: 'accepted'; id?: string; snapshotId: string }
  | { type: 'failed'; id?: string; code: string; message: string }
  | { type: 'done'; id?: string; status: ModelJob['status']; snapshotId: string | null };

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
  }[];
  scopes: string[];
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
  scopes: { scope: string | null; description: string | null }[];
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
