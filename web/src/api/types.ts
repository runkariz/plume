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

export type ItemKind = 'endpoint' | 'model' | 'guide' | 'auth' | 'app';
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
}

export interface BrowseItem {
  id: string;
  kind: ItemKind;
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
  logo: { text: string; color: string };
}

export type CoverageKind = 'direct' | 'derived' | 'absent';
export type Operation = 'read' | 'write';

export interface Concept {
  id: string;
  name: string;
  description: string;
  likelyFields: number;
  coverage: Record<string, CoverageKind>; // by api id
  operations: Operation[];
  difficulty: { tone: 'ok' | 'warn' | 'bad'; label: string };
  /** The documents behind the concept, per API (evidence the model is built from). */
  documents?: Record<string, string[]>;
}

export interface SuggestResponse {
  apis: ApiRef[];
  concepts: Concept[];
  notModeled: { count: number; summary: string };
}

export interface GenerateRequest {
  apis: string[];
  concept: string;
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

export interface ModelSnapshot {
  id: string;
  name: string;
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

export interface ModelListItem {
  id: string;
  name: string;
  concept: string;
  apis: string[];
  generatedAt: string;
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
  fields: {
    name: string;
    location: string;
    type: string | null;
    required: boolean;
    description: string | null;
  }[];
  scopes: string[];
}
