import { withPaths } from '@/pages/models/fields';
import { apiLabel, apiTitle } from '@/lib/names';
import { apiBaseUrl } from './config';
import { createSseParser } from './sse';
import {
  ApiError,
  type DocumentOut,
  type DraftIssue,
  type PinnedBy,
  type RemovalPreview,
  type RemoveApiRequest,
  type RemoveApiResult,
  type EvidencePage,
  type GenerateRequest,
  type GenerateJobResponse,
  type GenerateResponse,
  type ChangeItem,
  type Collection,
  type CollectionRef,
  type ModelJob,
  type ReleaseNotes,
  type ApiDisplayName,
  type MappingReport,
  type MappingReportAction,
  type MappingReportList,
  type MappingReportQuery,
  type MappingRoute,
  type Report,
  type ReportList,
  type ReportQuery,
  type ReportStatus,
  type ReleaseSummary,
  type VerifiedMapping,
  type VerifiedMappingQuery,
  type ChangesPage,
  type ChangesQuery,
  type ModelImpact,
  type PublicBuild,
  type ReportPage,
  type RollbackResult,
  type RelatedConcepts,
  type SetSessionRequest,
  type Supersedable,
  type SetSessionResponse,
  type SetSessionStatus,
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
  /**
   * Transition only: the models of old owner keys (POST so the keys stay out of URLs and logs), and the My models
   * links those keys became (`collections`), so the browser can switch to the link once.
   */
  listMyModels(
    ownerKeys: string[],
    signal?: AbortSignal,
  ): Promise<{ items: ModelListItem[]; collections?: { id: string; url: string }[] }>;
  /** A My models link: what is in it (404: no such link). */
  getCollection(id: string, signal?: AbortSignal): Promise<Collection>;
  /** Moves everything of the `from` links into `id` (400 over 500 items); the old links then say `mergedInto`. */
  mergeCollection(id: string, from: string[], signal?: AbortSignal): Promise<Collection>;
  /** Public poll of a session: has a draft been accepted for it yet? */
  getModelSession(sessionId: string, signal?: AbortSignal): Promise<ModelSessionStatus>;
  /** Maintainer token. 409 invalid_state unless the model is unreleased. */
  /** `supersedes`: ids of official models of the same concept this one replaces (none by default). */
  releaseModel(
    id: string,
    signal?: AbortSignal,
    opts?: { supersedes?: string[] },
  ): Promise<ModelSnapshot>;
  /** Maintainer token: retires older official models of the same concept after the fact (409: not official / not a candidate). */
  supersedeModels(id: string, supersedes: string[], signal?: AbortSignal): Promise<ModelSnapshot>;
  /** Maintainer token: the official models of the same concept this one could supersede (none on an older server). */
  listSupersedable(id: string, signal?: AbortSignal): Promise<Supersedable[]>;
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
   * Open to everyone: without the token the model is stored unlisted and joins a My models collection (`collection`:
   * the one sent, else a new one, answered as `collection`), with it unreleased (`collection: null`). A refused draft
   * rejects with an ApiError carrying `issues`.
   */
  submitModelDraft(
    sessionId: string,
    draft: unknown,
    signal?: AbortSignal,
    opts?: SaveOpts,
  ): Promise<{
    created: boolean;
    model: ModelSnapshot;
    visibility?: ModelVisibility;
    collection?: CollectionRef | null;
  }>;
  getSnapshot(id: string, signal?: AbortSignal): Promise<ModelSnapshot>;
  // model sets
  getModelSet(id: string, signal?: AbortSignal): Promise<ModelSet>;
  /** Released sets (the latest version of each); with the maintainer token also ?visibility=unreleased|all. */
  listModelSets(
    opts?: { visibility?: ModelVisibility | 'all' },
    signal?: AbortSignal,
  ): Promise<{ items: SetListItem[] }>;
  /** Maintainer token. 409 while relations are undecided or the set is not unreleased. */
  releaseModelSet(
    id: string,
    signal?: AbortSignal,
  ): Promise<{ set: ModelSet; releasedMembers: string[] }>;
  discardModelSet(id: string, signal?: AbortSignal): Promise<ModelSet>;
  /** Concepts related to one concept in these APIs, from documented evidence only (no LLM). */
  suggestRelated(
    req: { apis: string[]; concept: string; limit?: number; offset?: number },
    signal?: AbortSignal,
  ): Promise<RelatedConcepts>;
  /** For Claude: one model session per member (anyone; the set is stored unlisted without the token). */
  startSetSession(req: SetSessionRequest, signal?: AbortSignal): Promise<SetSessionResponse>;
  /**
   * Open to everyone, like a model draft: unlisted without the token (and in a My models collection), unreleased with
   * it. A refused draft rejects with an ApiError carrying `issues`.
   */
  submitSetDraft(
    sessionId: string,
    draft: unknown,
    signal?: AbortSignal,
    opts?: SaveOpts,
  ): Promise<{
    created: boolean;
    visibility?: ModelVisibility;
    collection?: CollectionRef | null;
    set: ModelSet;
  }>;
  /** Public poll: has the set been stored for this session yet? */
  getSetSession(id: string, signal?: AbortSignal): Promise<SetSessionStatus>;
  /** Maintainer token: Plume writes the members and proposes the relations (undecided). 202 with the job. */
  generateModelSet(req: SetSessionRequest, signal?: AbortSignal): Promise<GenerateJobResponse>;
  /**
   * Saves the chosen design of relations as a NEW version of the set (409 when `id` is not the latest version,
   * 422 {issues} when the design does not validate, 400 for anything but design fields).
   */
  saveSetRelations(
    id: string,
    relations: RelationEdit[],
    signal?: AbortSignal,
    opts?: SaveOpts,
  ): Promise<{
    created: boolean;
    visibility?: ModelVisibility;
    collection?: CollectionRef | null;
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
  /** Rename an API for display (maintainer): a name of 1 to 80 characters, or null to go back to the package's. */
  setApiDisplayName(
    api: string,
    name: string | null,
    signal?: AbortSignal,
  ): Promise<ApiDisplayName>;
  /** What removing an API would retire (maintainer): the models and sets that pin it. */
  getApiRemoval(api: string, signal?: AbortSignal): Promise<RemovalPreview>;
  /** Remove an API with everything it holds (maintainer); 409 api_in_use without `force` when something pins it. */
  removeApi(api: string, req: RemoveApiRequest, signal?: AbortSignal): Promise<RemoveApiResult>;
  // release notes users see (public): feature-detected, absent on a server without them
  /** The builds that have notes, newest first (empty: the API has none: no Changes tab). */
  getChangesTimeline(api: string, signal?: AbortSignal): Promise<PublicBuild[]>;
  getChanges(api: string, query: ChangesQuery, signal?: AbortSignal): Promise<ChangesPage>;
  /** Which mappings of a model a visible change touches. */
  getModelImpact(id: string, signal?: AbortSignal): Promise<ModelImpact>;
  getSetImpact(id: string, signal?: AbortSignal): Promise<ModelImpact>;
  // release notes (maintainer): the review of a build after it was published
  /** The notes of every build of an API that has some, newest first, with the review state and counts. */
  listReleaseNotes(api: string, signal?: AbortSignal): Promise<ReleaseSummary[]>;
  getReleaseNotes(api: string, build: string, signal?: AbortSignal): Promise<ReleaseNotes>;
  /** Reported questions, most reported first (maintainer). `enabled` says whether readers can report on this server. */
  listReports(q: ReportQuery, signal?: AbortSignal): Promise<ReportList>;
  getReport(id: string, signal?: AbortSignal): Promise<Report>;
  /** Mapping reports of canonical models, most reported first (maintainer). */
  listMappingReports(q: MappingReportQuery, signal?: AbortSignal): Promise<MappingReportList>;
  getMappingReport(id: string, signal?: AbortSignal): Promise<MappingReport>;
  /**
   * Accept (needs a suggestion that passed the validator; it becomes a verified mapping), reject (the reason is shown to
   * readers), route (to plume, stream or the owner) or reopen. A reason of at most 1,000 characters, required but for reopen.
   */
  actOnMappingReport(
    id: string,
    act: { action: MappingReportAction; reason?: string; route?: MappingRoute },
    signal?: AbortSignal,
  ): Promise<MappingReport>;
  /** The verified mappings (maintainer): accepted reports that are in force or suspended. */
  listVerifiedMappings(q: VerifiedMappingQuery, signal?: AbortSignal): Promise<VerifiedMapping[]>;
  /** Triage: the status, with a reason (at most 1,000 characters; the reasons of answered and out-of-scope are public). */
  setReportStatus(
    id: string,
    status: ReportStatus,
    reason: string | null,
    signal?: AbortSignal,
  ): Promise<Report>;
  /** More of one report group (the notes carry only its first 50), `limit` at most 200. */
  getReportPage(
    api: string,
    build: string,
    rule: string,
    cursor: number,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<ReportPage>;
  /** Keep the build; on a rolled-back build this rolls forward (409 when `latest` moved on). */
  keepRelease(
    api: string,
    build: string,
    note?: string,
    signal?: AbortSignal,
  ): Promise<ReleaseNotes>;
  /** Moves `latest` back to the build's base (reason required, at most 500 characters; 409 when not applicable). */
  rollbackRelease(
    api: string,
    build: string,
    reason: string,
    signal?: AbortSignal,
  ): Promise<RollbackResult>;
  /** The extraction report as one text for stream, built by the server (markdown or plain). */
  getReleaseIssues(
    api: string,
    build: string,
    format: 'markdown' | 'text',
    signal?: AbortSignal,
  ): Promise<string>;
  /** Makes a suspect/unknown item confirmed with a quote the server verifies (422 QUOTE_NOT_VERIFIED otherwise). */
  promoteChange(
    api: string,
    build: string,
    itemId: string,
    quote: string,
    signal?: AbortSignal,
  ): Promise<ChangeItem>;
  demoteChange(
    api: string,
    build: string,
    itemId: string,
    signal?: AbortSignal,
  ): Promise<ChangeItem>;
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

/** Saving without a maintainer token joins a My models collection: the one this browser holds, if any. */
export interface SaveOpts {
  collection?: string | null;
}

const collectionQuery = (opts?: SaveOpts) =>
  opts?.collection ? `?collection=${encodeURIComponent(opts.collection)}` : '';

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
    let pinnedBy: PinnedBy[] | undefined;
    try {
      const body: unknown = await res.json();
      message = errorMessage(body) ?? message;
      if (body && typeof body === 'object') {
        const b = body as Record<string, unknown>;
        if (typeof b.error === 'string') code = b.error;
        if (Array.isArray(b.issues)) issues = b.issues as DraftIssue[];
        if (Array.isArray(b.pinnedBy)) pinnedBy = b.pinnedBy as PinnedBy[];
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 429) {
      const wait = res.headers.get('Retry-After');
      message = `${message || 'Too many requests'}${wait ? ` Try again in ${wait} s.` : ''}`;
    }
    throw new ApiError(res.status, message || `Request failed (${res.status})`, {
      code,
      issues,
      pinnedBy,
    });
  }

  async function raw(
    path: string,
    init: {
      method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
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
      call<{ items: ModelListItem[]; collections?: { id: string; url: string }[] }>(
        '/v1/models/mine',
        {
          method: 'POST',
          body: { ownerKeys },
          signal,
        },
      ),
    getCollection: (id, signal) => call<Collection>(`/v1/collections/${enc(id)}`, { signal }),
    mergeCollection: (id, from, signal) =>
      call<Collection>(`/v1/collections/${enc(id)}/merge`, {
        method: 'POST',
        body: { from },
        signal,
      }),
    getModelSession: (sessionId, signal) =>
      call<ModelSessionStatus>(`/v1/models/sessions/${enc(sessionId)}`, { signal }),
    supersedeModels: (id, supersedes, signal) =>
      call<ModelSnapshot>(`/v1/models/${enc(id)}/supersede`, {
        method: 'POST',
        body: { supersedes },
        signal,
      }),
    listSupersedable: async (id, signal) => {
      try {
        const r = await call<{ items: Supersedable[] }>(`/v1/models/${enc(id)}/supersedable`, {
          signal,
        });
        return r.items ?? [];
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return []; // an older server: nothing to supersede
        throw e;
      }
    },
    releaseModel: (id, signal, opts) =>
      call<ModelSnapshot>(`/v1/models/${enc(id)}/release`, {
        method: 'POST',
        // a body only when something is superseded: a plain release is the request it always was
        ...(opts?.supersedes?.length ? { body: { supersedes: opts.supersedes } } : {}),
        signal,
      }),
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
    submitModelDraft: (sessionId, body, signal, opts) =>
      call<{
        created: boolean;
        model: ModelSnapshot;
        visibility?: ModelVisibility;
        collection?: CollectionRef | null;
      }>(`/v1/models/sessions/${enc(sessionId)}/draft${collectionQuery(opts)}`, {
        method: 'POST',
        body,
        signal,
      }),
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
    suggestRelated: async (req, signal) => {
      const r = await call<RelatedConcepts>('/v1/models/suggest-related', {
        method: 'POST',
        body: req,
        signal,
      });
      return { ...r, apis: r.apis.map(withLabel) };
    },
    startSetSession: (req, signal) =>
      call<SetSessionResponse>('/v1/model-sets/sessions', { method: 'POST', body: req, signal }),
    getSetSession: async (id, signal) => {
      // the server answers snake_case here; both spellings are accepted
      const r = await call<Record<string, unknown>>(`/v1/model-sets/sessions/${enc(id)}`, {
        signal,
      });
      const pick = (a: string, b: string) => r[a] ?? r[b];
      return {
        setSessionId: String(pick('set_session_id', 'setSessionId') ?? id),
        status: r.status === 'submitted' ? 'submitted' : 'open',
        setId: (pick('set_id', 'setId') as string | null | undefined) ?? null,
        visibility: (r.visibility as ModelVisibility | null | undefined) ?? null,
        concepts: Array.isArray(r.concepts) ? (r.concepts as string[]) : [],
      };
    },
    submitSetDraft: (sessionId, body, signal, opts) =>
      call<{
        created: boolean;
        visibility?: ModelVisibility;
        collection?: CollectionRef | null;
        set: ModelSet;
      }>(`/v1/model-sets/sessions/${enc(sessionId)}/draft${collectionQuery(opts)}`, {
        method: 'POST',
        body,
        signal,
      }),
    generateModelSet: (req, signal) =>
      call<GenerateJobResponse>('/v1/model-sets/generate', { method: 'POST', body: req, signal }),
    saveSetRelations: (id, relations, signal, opts) =>
      call<{
        created: boolean;
        visibility?: ModelVisibility;
        collection?: CollectionRef | null;
        set: ModelSet;
      }>(`/v1/model-sets/${enc(id)}/relations${collectionQuery(opts)}`, {
        method: 'POST',
        body: { relations },
        signal,
      }),
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
    getChangesTimeline: async (api, signal) => {
      const r = await call<{ items?: PublicBuild[] }>(`/v1/apis/${enc(api)}/changes/timeline`, {
        signal,
      });
      return r.items ?? [];
    },
    getChanges: (api, q, signal) => {
      const p = new URLSearchParams();
      if (q.build) p.set('build', q.build);
      if (q.since) p.set('since', q.since);
      if (q.breaking) p.set('breaking', 'true');
      if (q.kind) p.set('kind', q.kind);
      if (q.wordingOnly !== undefined) p.set('wordingOnly', String(q.wordingOnly));
      if (q.q?.trim()) p.set('q', q.q.trim());
      if (q.cursor !== undefined && q.cursor !== null) p.set('cursor', String(q.cursor));
      p.set('limit', String(q.limit ?? 100));
      return call<ChangesPage>(`/v1/apis/${enc(api)}/changes?${p.toString()}`, { signal });
    },
    getModelImpact: (id, signal) => call<ModelImpact>(`/v1/models/${enc(id)}/impact`, { signal }),
    getSetImpact: (id, signal) => call<ModelImpact>(`/v1/model-sets/${enc(id)}/impact`, { signal }),
    listReleaseNotes: async (api, signal) => {
      const r = await call<{ items?: ReleaseSummary[] }>(`/v1/apis/${enc(api)}/release-notes`, {
        signal,
      });
      return r.items ?? [];
    },
    listReports: async (q, signal) => {
      const p = new URLSearchParams();
      if (q.api) p.set('api', q.api);
      if (q.status) p.set('status', q.status);
      const qs = p.toString();
      const r = await call<Partial<ReportList>>(`/v1/maintainer/reports${qs ? `?${qs}` : ''}`, {
        signal,
      });
      return { reports: r.reports ?? [], enabled: r.enabled };
    },
    getReport: (id, signal) => call<Report>(`/v1/maintainer/reports/${enc(id)}`, { signal }),
    listMappingReports: async (q, signal) => {
      const p = new URLSearchParams();
      for (const k of ['api', 'concept', 'status', 'kind'] as const) if (q[k]) p.set(k, q[k]);
      const qs = p.toString();
      const r = await call<Partial<MappingReportList>>(
        `/v1/maintainer/mapping-reports${qs ? `?${qs}` : ''}`,
        { signal },
      );
      return { reports: r.reports ?? [], enabled: r.enabled };
    },
    getMappingReport: (id, signal) =>
      call<MappingReport>(`/v1/maintainer/mapping-reports/${enc(id)}`, { signal }),
    actOnMappingReport: (id, act, signal) =>
      call<MappingReport>(`/v1/maintainer/mapping-reports/${enc(id)}`, {
        method: 'PATCH',
        body: {
          action: act.action,
          ...(act.reason ? { reason: act.reason } : {}),
          ...(act.route ? { route: act.route } : {}),
        },
        signal,
      }),
    listVerifiedMappings: async (q, signal) => {
      const p = new URLSearchParams();
      for (const k of ['api', 'concept', 'status'] as const) if (q[k]) p.set(k, q[k]);
      const qs = p.toString();
      const r = await call<{ mappings?: VerifiedMapping[] }>(
        `/v1/maintainer/verified-mappings${qs ? `?${qs}` : ''}`,
        { signal },
      );
      return r.mappings ?? [];
    },
    setReportStatus: (id, status, reason, signal) =>
      call<Report>(`/v1/maintainer/reports/${enc(id)}`, {
        method: 'PATCH',
        body: reason ? { status, reason } : { status },
        signal,
      }),
    getReleaseNotes: (api, build, signal) =>
      call<ReleaseNotes>(`/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes`, { signal }),
    getReportPage: (api, build, rule, cursor, limit = 50, signal) =>
      call<ReportPage>(
        `/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/report/${enc(rule)}?cursor=${cursor}&limit=${limit}`,
        { signal },
      ),
    setApiDisplayName: (api, name, signal) =>
      call<ApiDisplayName>(`/v1/apis/${enc(api)}/display`, {
        method: 'PUT',
        body: { name },
        signal,
      }),
    getApiRemoval: (api, signal) =>
      call<RemovalPreview>(`/v1/apis/${enc(api)}/removal`, { signal }),
    removeApi: (api, req, signal) =>
      call<RemoveApiResult>(`/v1/apis/${enc(api)}`, { method: 'DELETE', body: req, signal }),
    keepRelease: (api, build, note, signal) =>
      call<ReleaseNotes>(`/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/keep`, {
        method: 'POST',
        body: note ? { note } : {},
        signal,
      }),
    rollbackRelease: (api, build, reason, signal) =>
      call<RollbackResult>(`/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/rollback`, {
        method: 'POST',
        body: { reason },
        signal,
      }),
    getReleaseIssues: async (api, build, format, signal) =>
      (
        await raw(
          `/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/issues?format=${format}`,
          { signal, accept: format === 'markdown' ? 'text/markdown' : 'text/plain' },
        )
      ).text(),
    promoteChange: (api, build, itemId, quote, signal) =>
      call<ChangeItem>(
        `/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/items/${enc(itemId)}/promote`,
        { method: 'POST', body: { quote }, signal },
      ),
    demoteChange: (api, build, itemId, signal) =>
      call<ChangeItem>(
        `/v1/apis/${enc(api)}/builds/${enc(build)}/release-notes/items/${enc(itemId)}/demote`,
        { method: 'POST', signal },
      ),
    watchJob: watch,
  };
}
