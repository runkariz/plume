/**
 * Hand-written types for the Plume HTTP API (W1 stub).
 * Replaced by types generated from the backend OpenAPI once plume-6f publishes it (P3).
 */
export type ApiStatus =
  { kind: 'ready'; recallAt5: number } | { kind: 'updating'; progress: number };

export interface ApiSummary {
  id: string;
  name: string;
  category: string;
  summary: string;
  endpoints: number;
  models: number;
  guides: number;
  docsAsOf: string; // ISO date
  status: ApiStatus;
  logo: { text: string; color: string };
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

export type ItemKind = 'endpoint' | 'model' | 'guide';
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface ApiDetail extends ApiSummary {
  chunks: number;
  isLive: boolean;
  tag: string; // e.g. "latest"
  quality: {
    recallAt5: number;
    mrr: number;
    inventedEndpoints: number;
    goldQuestions: number;
    evaluatedAt: string; // ISO date
  };
  index: { embedding: string; dimensions: number; store: string; build: string };
  connect: { claudeCode: string };
}

export interface BrowseItem {
  id: string;
  kind: ItemKind;
  title: string;
  method?: HttpMethod;
  path?: string;
  resource: string;
}

export interface BrowseResult {
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
  denseRank: number | null;
  textRank: number | null;
  denseScore: number; // 0..1, for the bar
  textScore: number; // 0..1
  fused: number;
}

export interface TraceStep {
  source: 'gemini' | 'postgres' | 'plume';
  label: string;
  ms: number;
}

export interface SearchResponse {
  api: string;
  docsAsOf: string;
  results: SearchHit[];
  trace: TraceStep[];
  totalMs: number;
  /** The JSON Claude receives from the reader tool, pretty-printed by the server. */
  claudePayload: string;
}

export interface AskResponse {
  api: string;
  docsAsOf: string;
  question: string;
  /** Retrieval only: Plume returns the passages Claude would write the answer from. */
  passages: { id: string; title: string; quote: string; sourceUrl: string }[];
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
  paramChecks: { name: string; found: boolean; where: string | null }[];
  checked: { endpoints: number; models: number };
}
