import { withPaths } from '@/pages/models/fields';
import { apiLabel, apiTitle } from '@/lib/names';
import { apiBaseUrl } from './config';
import { createSseParser } from './sse';
import {
  ApiError,
  type DocumentOut,
  type DraftIssue,
  type EvidencePage,
  type GenerateRequest,
  type GenerateJobResponse,
  type GenerateResponse,
  type ModelJob,
  type ModelJobEvent,
  type ModelSet,
  type RelationEdit,
  type SetListItem,
  type ModelSessionStatus,
  type ModelVisibility,
  type ModelContext,
  type ModelListItem,
  type Job,
  type ModelSnapshot,
  type SuggestQuery,
  type SuggestResponse,
  type JobEvent,
  type MaintainerIdentity,
  type ReviewRequest,
  type ApiDetail,
  type ApiList,
  type AuthList,
  type AuthSchemeDetail,
  type EnvironmentsOut,
  type McpOut,
  type TriggerDetail,
  type TriggerList,
  type AskResponse,
  type BrowseResult,
  type CheckCallRequest,
  type CheckCallResponse,
  type ItemKind,
  type SearchRequest,
  type SearchResponse,
} from './types';

export interface PlumeApi {
  /** The API base URL this client talks to (no trailing slash). */
  readonly baseUrl: string;
  listApis(signal?: AbortSignal): Promise<ApiList>;
  getApi(id: string, signal?: AbortSignal): Promise<ApiDetail>;
  getDocument(api: string, docId: string, signal?: AbortSignal): Promise<DocumentOut>;
  getAuth(api: string, signal?: AbortSignal): Promise<AuthList>;
  getAuthScheme(api: string, schemeId: string, signal?: AbortSignal): Promise<AuthSchemeDetail>;
  getTriggers(
    api: string,
    q?: { limit?: number; offset?: number },
    signal?: AbortSignal,
  ): Promise<TriggerList>;
  /** `key` is the trigger key (it contains "/"); it is URL-encoded here. */
  getTrigger(api: string, key: string, signal?: AbortSignal): Promise<TriggerDetail>;
  getEnvironments(api: string, signal?: AbortSignal): Promise<EnvironmentsOut>;
  getMcp(api: string, signal?: AbortSignal): Promise<McpOut>;
  browse(
    id: string,
    q: { kind?: ItemKind; query?: string; limit?: number; tag?: string },
    signal?: AbortSignal,
  ): Promise<BrowseResult>;
  search(id: string, req: SearchRequest, signal?: AbortSignal): Promise<SearchResponse>;
  ask(id: string, question: string, signal?: AbortSignal): Promise<AskResponse>;
  checkCall(id: string, req: CheckCallRequest, signal?: AbortSignal): Promise<CheckCallResponse>;
  // canonical models
  listModelCandidates(signal?: AbortSignal): Promise<ApiList>;
  suggestModels(
    apis: string[],
    query?: SuggestQuery,
    signal?: AbortSignal,
  ): Promise<SuggestResponse>;
  /**
   * Without the maintainer token: a session for Claude (the model is stored unlisted). With it: a server-side job
   * (202) unless `engine: "claude"`.
   */
  generateModel(
    req: GenerateRequest,
    signal?: AbortSignal,
  ): Promise<GenerateResponse | GenerateJobResponse>;
  /**
   * Released (official) models, newest first; pass an API id to list the models that use it. With the maintainer
   * token, `visibility` also lists unreleased models.
   */
  listModels(
    api?: string,
    signal?: AbortSignal,
    opts?: { visibility?: ModelVisibility | 'all' },
  ): Promise<{ items: ModelListItem[] }>;
  /** The models of the owner keys this browser holds (POST so the keys stay out of URLs and logs). */
  listMyModels(ownerKeys: string[], signal?: AbortSignal): Promise<{ items: ModelListItem[] }>;
  /** Public poll of a session: has a draft been accepted for it yet? */
  getModelSession(sessionId: string, signal?: AbortSignal): Promise<ModelSessionStatus>;
  /** Maintainer token. 409 invalid_state unless the model is unreleased. */
  releaseModel(id: string, signal?: AbortSignal): Promise<ModelSnapshot>;
  discardModel(id: string, signal?: AbortSignal): Promise<ModelSnapshot>;
  getModelJob(jobId: string, signal?: AbortSignal): Promise<ModelJob>;
  /** Streams a generation job; resolves after `done`, resumes with Last-Event-ID, rejects after repeated loss. */
  watchModelJob(
    jobId: string,
    onEvent: (e: ModelJobEvent) => void,
    signal?: AbortSignal,
  ): Promise<void>;
  /** The compact evidence index Claude reads for a session (snake_case JSON from the server). */
  getModelContext(sessionId: string, signal?: AbortSignal): Promise<ModelContext>;
  /** One page of the fields of an API's documents in a session; follow `next_cursor` for more. */
  getModelEvidence(
    sessionId: string,
    q: { api: string; docs?: string[]; cursor?: number },
    signal?: AbortSignal,
  ): Promise<EvidencePage>;
  /**
   * Open to everyone: without the token the model is stored unlisted (a new lineage returns an `ownerKey`, shown
   * once), with it unreleased. A refused draft rejects with an ApiError carrying `issues`.
   */
  submitModelDraft(
    sessionId: string,
    draft: unknown,
    signal?: AbortSignal,
  ): Promise<{
    created: boolean;
    model: ModelSnapshot;
    visibility?: ModelVisibility;
    ownerKey?: string;
  }>;
  getSnapshot(id: string, signal?: AbortSignal): Promise<ModelSnapshot>;
  // model sets
  getModelSet(id: string, signal?: AbortSignal): Promise<ModelSet>;
  /** Released sets (the latest version of each); with the maintainer token also ?visibility=unreleased|all. */
  listModelSets(
    opts?: { visibility?: ModelVisibility | 'all' },
    signal?: AbortSignal,
  ): Promise<{ items: SetListItem[] }>;
  listMyModelSets(ownerKeys: string[], signal?: AbortSignal): Promise<{ items: SetListItem[] }>;
  /** Maintainer token. 409 while relations are undecided or the set is not unreleased. */
  releaseModelSet(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ set: ModelSet; releasedMembers: string[] }>;
  discardModelSet(id: string, signal?: AbortSignal): Promise<ModelSet>;
  /**
   * Saves the chosen design of relations as a NEW version of the set (409 when `id` is not the latest version,
   * 422 {issues} when the design does not validate, 400 for anything but design fields).
   */
  saveSetRelations(
    id: string,
    relations: RelationEdit[],
    signal?: AbortSignal,
  ): Promise<{
    created: boolean;
    visibility?: ModelVisibility;
    ownerKey: string | null;
    set: ModelSet;
  }>;
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
    /** Called when the API answers 401 to the maintainer key this client sent (not to a key being verified). */
    onUnauthorized?: () => void;
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
    // the session's own key was refused (a key being verified at sign-in is not the session's): it is no longer valid
    if (res.status === 401 && init.key === undefined && opts.maintainerKey?.())
      opts.onUnauthorized?.();
    if (!res.ok) await fail(res);
    return res;
  }

  async function call<T>(path: string, init: Parameters<typeof raw>[1] = {}): Promise<T> {
    return (await (await raw(path, init)).json()) as T;
  }

  /**
   * Reads an SSE stream until `isDone` says an event is the last one. It reconnects with Last-Event-ID after a
   * lost connection (a few times), and throws when the stream ends without a last event.
   */
  async function stream<E extends { id?: string }>(
    path: string,
    parse: (m: { event: string; data: string }) => E,
    isDone: (e: E) => boolean,
    onEvent: (e: E) => void,
    signal?: AbortSignal,
  ) {
    let lastId: string | undefined;
    let finished = false;
    let failures = 0;
    while (!finished) {
      try {
        const res = await raw(path, {
          signal,
          accept: 'text/event-stream',
          headers: lastId ? { 'Last-Event-ID': lastId } : {},
        });
        if (!res.body) throw new Error('The event stream has no body');
        const parser = createSseParser((m) => {
          if (m.id) lastId = m.id;
          const e = parse(m);
          if (m.id) e.id = m.id;
          if (isDone(e)) finished = true;
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
        if (!finished) throw new Error('The event stream closed before it finished');
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

  const watch = (id: string, onEvent: (e: JobEvent) => void, signal?: AbortSignal) =>
    stream<JobEvent>(
      `/v1/jobs/${enc(id)}/events`,
      (m) => JSON.parse(m.data) as JobEvent,
      (e) => e.type === 'done',
      onEvent,
      signal,
    );

  // the model events carry their type in the SSE `event:` name; the data may or may not repeat it
  const watchModel = (id: string, onEvent: (e: ModelJobEvent) => void, signal?: AbortSignal) =>
    stream<ModelJobEvent>(
      `/v1/models/jobs/${enc(id)}/events`,
      (m) => ({ ...(JSON.parse(m.data) as object), type: m.event }) as ModelJobEvent,
      (e) => e.type === 'done',
      onEvent,
      signal,
    );

  return {
    baseUrl,
    listApis: async (signal) => normaliseList(await call<ApiList>('/v1/apis', { signal })),
    getApi: async (id, signal) =>
      withTitle(await call<ApiDetail>(`/v1/apis/${enc(id)}`, { signal })),
    getDocument: (api, docId, signal) =>
      call<DocumentOut>(`/v1/apis/${enc(api)}/documents/${enc(docId)}`, { signal }),
    getAuth: (api, signal) => call<AuthList>(`/v1/apis/${enc(api)}/auth`, { signal }),
    getAuthScheme: (api, schemeId, signal) =>
      call<AuthSchemeDetail>(`/v1/apis/${enc(api)}/auth/${enc(schemeId)}`, { signal }),
    getTriggers: (api, q = {}, signal) => {
      const p = new URLSearchParams();
      if (q.limit) p.set('limit', String(q.limit));
      if (q.offset) p.set('offset', String(q.offset));
      const qs = p.toString();
      return call<TriggerList>(`/v1/apis/${enc(api)}/triggers${qs ? `?${qs}` : ''}`, { signal });
    },
    getTrigger: (api, key, signal) =>
      call<TriggerDetail>(`/v1/apis/${enc(api)}/triggers/${enc(key)}`, { signal }),
    getMcp: (api, signal) => call<McpOut>(`/v1/apis/${enc(api)}/mcp`, { signal }),
    getEnvironments: (api, signal) =>
      call<EnvironmentsOut>(`/v1/apis/${enc(api)}/environments`, { signal }),
    browse: (id, q, signal) => {
      const p = new URLSearchParams();
      if (q.kind) p.set('kind', q.kind);
      if (q.query) p.set('q', q.query);
      if (q.limit) p.set('limit', String(q.limit));
      if (q.tag) p.set('tag', q.tag);
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
    suggestModels: async (apis, query = {}, signal) => {
      // only what was asked for is sent: the server's defaults (multi, 24 per page) apply to the rest
      const body: Record<string, unknown> = { apis };
      if (query.q) body.q = query.q;
      if (query.only && query.only !== 'multi') body.only = query.only;
      if (query.require?.length) body.require = query.require;
      if (query.inAll) body.inAll = true;
      if (query.writeOnly) body.writeOnly = true;
      if (query.limit) body.limit = query.limit;
      if (query.offset) body.offset = query.offset;
      const r = await call<SuggestResponse>('/v1/models/suggest', { method: 'POST', body, signal });
      return { ...r, apis: r.apis.map(withLabel) };
    },
    generateModel: (body, signal) =>
      call<GenerateResponse>('/v1/models/generate', { method: 'POST', body, signal }),
    listModels: (api, signal, opts = {}) => {
      const p = new URLSearchParams();
      if (api) p.set('api', api);
      if (opts.visibility) p.set('visibility', opts.visibility);
      const qs = p.toString();
      return call<{ items: ModelListItem[] }>(`/v1/models${qs ? `?${qs}` : ''}`, { signal });
    },
    listMyModels: (ownerKeys, signal) =>
      call<{ items: ModelListItem[] }>('/v1/models/mine', {
        method: 'POST',
        body: { ownerKeys },
        signal,
      }),
    getModelSession: (sessionId, signal) =>
      call<ModelSessionStatus>(`/v1/models/sessions/${enc(sessionId)}`, { signal }),
    releaseModel: (id, signal) =>
      call<ModelSnapshot>(`/v1/models/${enc(id)}/release`, { method: 'POST', signal }),
    discardModel: (id, signal) =>
      call<ModelSnapshot>(`/v1/models/${enc(id)}/discard`, { method: 'POST', signal }),
    getModelJob: (jobId, signal) => call<ModelJob>(`/v1/models/jobs/${enc(jobId)}`, { signal }),
    watchModelJob: watchModel,
    getModelContext: (sessionId, signal) =>
      call<ModelContext>(`/v1/models/sessions/${enc(sessionId)}/context`, { signal }),
    getModelEvidence: (sessionId, q, signal) => {
      const p = new URLSearchParams({ api: q.api });
      for (const d of q.docs ?? []) p.append('doc', d);
      if (q.cursor !== undefined) p.set('cursor', String(q.cursor));
      return call<EvidencePage>(`/v1/models/sessions/${enc(sessionId)}/evidence?${p}`, { signal });
    },
    submitModelDraft: (sessionId, body, signal) =>
      call<{
        created: boolean;
        model: ModelSnapshot;
        visibility?: ModelVisibility;
        ownerKey?: string;
      }>(`/v1/models/sessions/${enc(sessionId)}/draft`, { method: 'POST', body, signal }),
    getSnapshot: async (id, signal) => {
      const m = await call<ModelSnapshot>(`/v1/models/${enc(id)}`, { signal });
      return withPaths({ ...m, inputs: m.inputs.map(withLabel) });
    },
    getModelSet: async (id, signal) => {
      const s = await call<ModelSet>(`/v1/model-sets/${enc(id)}`, { signal });
      return { ...s, inputs: s.inputs.map(withLabel) };
    },
    listModelSets: (opts = {}, signal) =>
      call<{ items: SetListItem[] }>(
        `/v1/model-sets${opts.visibility ? `?visibility=${enc(opts.visibility)}` : ''}`,
        { signal },
      ),
    listMyModelSets: (ownerKeys, signal) =>
      call<{ items: SetListItem[] }>('/v1/model-sets/mine', {
        method: 'POST',
        body: { ownerKeys },
        signal,
      }),
    releaseModelSet: (id, signal) =>
      call<{ set: ModelSet; releasedMembers: string[] }>(`/v1/model-sets/${enc(id)}/release`, {
        method: 'POST',
        signal,
      }),
    discardModelSet: async (id, signal) => {
      const r = await call<ModelSet | { set: ModelSet }>(`/v1/model-sets/${enc(id)}/discard`, {
        method: 'POST',
        signal,
      });
      return 'set' in r ? r.set : r;
    },
    saveSetRelations: (id, relations, signal) =>
      call<{
        created: boolean;
        visibility?: ModelVisibility;
        ownerKey: string | null;
        set: ModelSet;
      }>(`/v1/model-sets/${enc(id)}/relations`, { method: 'POST', body: { relations }, signal }),
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
