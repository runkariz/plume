import { apiLabel, apiTitle } from '@/lib/names';
import { apiBaseUrl } from './config';
import { createSseParser } from './sse';
import {
  ApiError,
  type DocumentOut,
  type DraftIssue,
  type EvidencePage,
  type GenerateRequest,
  type GenerateResponse,
  type ModelContext,
  type ModelListItem,
  type Job,
  type ModelSnapshot,
  type SuggestResponse,
  type JobEvent,
  type MaintainerIdentity,
  type ReviewRequest,
  type ApiDetail,
  type ApiList,
  type AskResponse,
  type BrowseResult,
  type CheckCallRequest,
  type CheckCallResponse,
  type ItemKind,
  type SearchRequest,
  type SearchResponse,
} from './types';

export interface PlumeApi {
  listApis(signal?: AbortSignal): Promise<ApiList>;
  getApi(id: string, signal?: AbortSignal): Promise<ApiDetail>;
  getDocument(api: string, docId: string, signal?: AbortSignal): Promise<DocumentOut>;
  browse(
    id: string,
    q: { kind?: ItemKind; query?: string; limit?: number },
    signal?: AbortSignal,
  ): Promise<BrowseResult>;
  search(id: string, req: SearchRequest, signal?: AbortSignal): Promise<SearchResponse>;
  ask(id: string, question: string, signal?: AbortSignal): Promise<AskResponse>;
  checkCall(id: string, req: CheckCallRequest, signal?: AbortSignal): Promise<CheckCallResponse>;
  // canonical models
  listModelCandidates(signal?: AbortSignal): Promise<ApiList>;
  suggestModels(apis: string[], signal?: AbortSignal): Promise<SuggestResponse>;
  generateModel(req: GenerateRequest, signal?: AbortSignal): Promise<GenerateResponse>;
  listModels(api?: string, signal?: AbortSignal): Promise<{ items: ModelListItem[] }>;
  /** The compact evidence index Claude reads for a session (snake_case JSON from the server). */
  getModelContext(sessionId: string, signal?: AbortSignal): Promise<ModelContext>;
  /** One page of the fields of an API's documents in a session; follow `next_cursor` for more. */
  getModelEvidence(
    sessionId: string,
    q: { api: string; docs?: string[]; cursor?: number },
    signal?: AbortSignal,
  ): Promise<EvidencePage>;
  /** Maintainer token required. A refused draft rejects with an ApiError carrying `issues`. */
  submitModelDraft(
    sessionId: string,
    draft: unknown,
    signal?: AbortSignal,
  ): Promise<{ created: boolean; model: ModelSnapshot }>;
  getSnapshot(id: string, signal?: AbortSignal): Promise<ModelSnapshot>;
  // maintainer (the key is sent as a bearer token)
  verifyMaintainer(key: string, signal?: AbortSignal): Promise<MaintainerIdentity>;
  uploadPackage(file: File, signal?: AbortSignal): Promise<Job>;
  getJob(id: string, signal?: AbortSignal): Promise<Job>;
  reviewJob(id: string, req: ReviewRequest, signal?: AbortSignal): Promise<Job>;
  startBuild(id: string, signal?: AbortSignal): Promise<Job>;
  publishJob(id: string, signal?: AbortSignal): Promise<Job>;
  discardJob(id: string, signal?: AbortSignal): Promise<Job>;
  downloadDump(id: string, signal?: AbortSignal): Promise<{ blob: Blob; filename: string | null }>;
  /** Streams build events; resolves after a `done` event, rejects after repeated connection loss. */
  watchJob(id: string, onEvent: (e: JobEvent) => void, signal?: AbortSignal): Promise<void>;
}

/** Names are normalised once, where they come in, so every page shows the display form. */
function withLabel<T extends { id: string; shortName: string }>(a: T): T {
  return { ...a, shortName: apiLabel(a) };
}
function withTitle<T extends { id: string; name: string }>(a: T): T {
  return { ...a, name: apiTitle(a) };
}
function normaliseList(list: ApiList): ApiList {
  return { ...list, items: list.items.map(withTitle) };
}

export function errorMessage(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const b = body as Record<string, unknown>;
  if (typeof b.message === 'string') return b.message;
  if (typeof b.detail === 'string') return b.detail;
  if (Array.isArray(b.detail)) {
    const first: unknown = b.detail[0];
    if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string')
      return first.msg;
  }
  return undefined;
}

/** Typed fetch client. The maintainer key, when present, is passed in by the caller (never stored here). */
export function createApiClient(
  baseUrl: string = apiBaseUrl(),
  opts: {
    maintainerKey?: () => string | null;
    fetchImpl?: typeof fetch;
    /** Delay before reconnect attempt n (1-based) of the event stream; tests pass () => 0. */
    retryDelayMs?: (attempt: number) => number;
  } = {},
): PlumeApi {
  const enc = encodeURIComponent;
  const doFetch = opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));

  function authHeaders(keyOverride?: string): Record<string, string> {
    const key = keyOverride ?? opts.maintainerKey?.();
    return key ? { Authorization: `Bearer ${key}` } : {};
  }

  /** Plume errors are {error, message}; FastAPI validation errors are {detail: [...]}; mocks use {detail: string}. */
  async function fail(res: Response): Promise<never> {
    let message = res.statusText;
    let code: string | undefined;
    let issues: DraftIssue[] | undefined;
    try {
      const body: unknown = await res.json();
      message = errorMessage(body) ?? message;
      if (body && typeof body === 'object') {
        const b = body as Record<string, unknown>;
        if (typeof b.error === 'string') code = b.error;
        if (Array.isArray(b.issues)) issues = b.issues as DraftIssue[];
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 429) {
      const wait = res.headers.get('Retry-After');
      message = `${message || 'Too many requests'}${wait ? ` Try again in ${wait} s.` : ''}`;
    }
    throw new ApiError(res.status, message || `Request failed (${res.status})`, { code, issues });
  }

  async function raw(
    path: string,
    init: {
      method?: 'GET' | 'POST';
      body?: unknown;
      form?: FormData;
      signal?: AbortSignal;
      key?: string;
      accept?: string;
      headers?: Record<string, string>;
    } = {},
  ): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: init.accept ?? 'application/json',
      ...authHeaders(init.key),
      ...init.headers,
    };
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await doFetch(`${baseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.form ?? (init.body === undefined ? undefined : JSON.stringify(init.body)),
      signal: init.signal,
    });
    if (!res.ok) await fail(res);
    return res;
  }

  async function call<T>(path: string, init: Parameters<typeof raw>[1] = {}): Promise<T> {
    return (await (await raw(path, init)).json()) as T;
  }

  async function watch(id: string, onEvent: (e: JobEvent) => void, signal?: AbortSignal) {
    let lastId: string | undefined;
    let finished = false;
    let failures = 0;
    while (!finished) {
      try {
        const res = await raw(`/v1/jobs/${enc(id)}/events`, {
          signal,
          accept: 'text/event-stream',
          headers: lastId ? { 'Last-Event-ID': lastId } : {},
        });
        if (!res.body) throw new Error('The event stream has no body');
        const parser = createSseParser((m) => {
          if (m.id) lastId = m.id;
          const e = JSON.parse(m.data) as JobEvent;
          if (m.id) e.id = m.id;
          if (e.type === 'done') finished = true;
          onEvent(e);
        });
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          failures = 0;
          parser.push(dec.decode(value, { stream: true }));
        }
        if (!finished) throw new Error('The event stream closed before the build finished');
      } catch (e) {
        if (signal?.aborted) return;
        if (e instanceof ApiError && e.status < 500) throw e;
        failures += 1;
        if (failures > 5) throw e instanceof Error ? e : new Error(String(e));
        const wait = opts.retryDelayMs?.(failures) ?? Math.min(500 * failures, 3000);
        await new Promise((r) => setTimeout(r, wait));
      }
    }
  }

  return {
    listApis: async (signal) => normaliseList(await call<ApiList>('/v1/apis', { signal })),
    getApi: async (id, signal) =>
      withTitle(await call<ApiDetail>(`/v1/apis/${enc(id)}`, { signal })),
    getDocument: (api, docId, signal) =>
      call<DocumentOut>(`/v1/apis/${enc(api)}/documents/${enc(docId)}`, { signal }),
    browse: (id, q, signal) => {
      const p = new URLSearchParams();
      if (q.kind) p.set('kind', q.kind);
      if (q.query) p.set('q', q.query);
      if (q.limit) p.set('limit', String(q.limit));
      const qs = p.toString();
      return call<BrowseResult>(`/v1/apis/${enc(id)}/items${qs ? `?${qs}` : ''}`, { signal });
    },
    search: (id, body, signal) =>
      call<SearchResponse>(`/v1/apis/${enc(id)}/search`, { method: 'POST', body, signal }),
    ask: (id, question, signal) =>
      call<AskResponse>(`/v1/apis/${enc(id)}/ask`, { method: 'POST', body: { question }, signal }),
    checkCall: (id, body, signal) =>
      call<CheckCallResponse>(`/v1/apis/${enc(id)}/check-call`, { method: 'POST', body, signal }),
    listModelCandidates: async (signal) =>
      normaliseList(await call<ApiList>('/v1/models/candidates', { signal })),
    suggestModels: async (apis, signal) => {
      const r = await call<SuggestResponse>('/v1/models/suggest', {
        method: 'POST',
        body: { apis },
        signal,
      });
      return { ...r, apis: r.apis.map(withLabel) };
    },
    generateModel: (body, signal) =>
      call<GenerateResponse>('/v1/models/generate', { method: 'POST', body, signal }),
    listModels: (api, signal) =>
      call<{ items: ModelListItem[] }>(`/v1/models${api ? `?api=${enc(api)}` : ''}`, { signal }),
    getModelContext: (sessionId, signal) =>
      call<ModelContext>(`/v1/models/sessions/${enc(sessionId)}/context`, { signal }),
    getModelEvidence: (sessionId, q, signal) => {
      const p = new URLSearchParams({ api: q.api });
      for (const d of q.docs ?? []) p.append('doc', d);
      if (q.cursor !== undefined) p.set('cursor', String(q.cursor));
      return call<EvidencePage>(`/v1/models/sessions/${enc(sessionId)}/evidence?${p}`, { signal });
    },
    submitModelDraft: (sessionId, body, signal) =>
      call<{ created: boolean; model: ModelSnapshot }>(
        `/v1/models/sessions/${enc(sessionId)}/draft`,
        { method: 'POST', body, signal },
      ),
    getSnapshot: async (id, signal) => {
      const m = await call<ModelSnapshot>(`/v1/models/${enc(id)}`, { signal });
      return { ...m, inputs: m.inputs.map(withLabel) };
    },
    verifyMaintainer: (key, signal) =>
      call<MaintainerIdentity>('/v1/maintainer/me', { key, signal }),
    uploadPackage: (file, signal) => {
      const form = new FormData();
      form.append('file', file, file.name);
      return call<Job>('/v1/packages', { method: 'POST', form, signal });
    },
    getJob: (id, signal) => call<Job>(`/v1/jobs/${enc(id)}`, { signal }),
    reviewJob: (id, body, signal) =>
      call<Job>(`/v1/jobs/${enc(id)}/review`, { method: 'POST', body, signal }),
    startBuild: (id, signal) => call<Job>(`/v1/jobs/${enc(id)}/build`, { method: 'POST', signal }),
    publishJob: (id, signal) =>
      call<Job>(`/v1/jobs/${enc(id)}/publish`, { method: 'POST', signal }),
    discardJob: (id, signal) =>
      call<Job>(`/v1/jobs/${enc(id)}/discard`, { method: 'POST', signal }),
    downloadDump: async (id, signal) => {
      const res = await raw(`/v1/jobs/${enc(id)}/dump`, { signal, accept: 'application/gzip' });
      const disposition = res.headers.get('Content-Disposition') ?? '';
      const filename = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)?.[1] ?? null;
      return { blob: await res.blob(), filename: filename ? decodeURIComponent(filename) : null };
    },
    watchJob: watch,
  };
}
