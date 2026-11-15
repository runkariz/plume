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
  models: number;
  guides: number;
  docsAsOf: string | null; // ISO date; null while unpublished
  status: ApiStatus;
  logo: { text: string; color: string; url?: string | null };
}

export interface ApiList {
  items: ApiSummary[];
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
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
    inventedEndpoints: number;
    goldQuestions: number;
    evaluatedAt: string; // ISO date
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
  method?: HttpMethod;
  path?: string;
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
  liveBuild: string | null;
  stagedBuild: string;
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
  | { type: 'log'; id: string; t: string; source: EventSource; message: string }
  | { type: 'step'; id: string; key: StepKey; status: StepStatus; detail: string }
  | { type: 'progress'; id: string; done: number; total: number; etaSeconds: number | null }
  | { type: 'service'; id: string; service: 'postgres' | 'gemini'; detail: string }
  | { type: 'done'; id: string; status: 'staged' | 'failed'; message?: string };

// ---- canonical models (W4) ----

export interface ApiRef {
  id: string;
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
  transform?: string;
  fetch?: { endpoint: string };
  join?: string[];
  evidence?: { quote: string; anchor: string }[];
}

export interface ModelField {
  name: string;
  type: string;
  required: boolean;
  support: Record<string, FieldSupport>; // by api id
  sources: Record<string, FieldSource>;
}

export interface ModelSnapshot {
  id: string;
  name: string;
  description: string;
  status: 'generated_unverified';
  generatedAt: string;
  promptVersion: string;
  inputs: (ApiRef & { build: string })[];
  fields: ModelField[];
  /** Question text may contain **bold** spans. */
  openQuestions: { question: string; detail?: string }[];
  coverage: Record<string, { mapped: number; total: number }>;
  citations: { checked: number; found: number; missing: string[] };
}
