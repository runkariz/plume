import { apiBaseUrl } from './config';
import {
  ApiError,
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
  browse(
    id: string,
    q: { kind?: ItemKind; query?: string; limit?: number },
    signal?: AbortSignal,
  ): Promise<BrowseResult>;
  search(id: string, req: SearchRequest, signal?: AbortSignal): Promise<SearchResponse>;
  ask(id: string, question: string, signal?: AbortSignal): Promise<AskResponse>;
  checkCall(id: string, req: CheckCallRequest, signal?: AbortSignal): Promise<CheckCallResponse>;
}

/** Typed fetch client. The maintainer key, when present, is passed in by the caller (never stored here). */
export function createApiClient(
  baseUrl: string = apiBaseUrl(),
  opts: { maintainerKey?: () => string | null; fetchImpl?: typeof fetch } = {},
): PlumeApi {
  const doFetch = opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));

  async function call<T>(
    path: string,
    init: { method?: 'GET' | 'POST'; body?: unknown; signal?: AbortSignal } = {},
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';
    const key = opts.maintainerKey?.();
    if (key) headers.Authorization = `Bearer ${key}`;
    const res = await doFetch(`${baseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body: unknown = await res.json();
        if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string')
          detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, detail || `Request failed (${res.status})`);
    }
    return (await res.json()) as T;
  }

  const enc = encodeURIComponent;
  return {
    listApis: (signal) => call<ApiList>('/v1/apis', { signal }),
    getApi: (id, signal) => call<ApiDetail>(`/v1/apis/${enc(id)}`, { signal }),
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
  };
}
