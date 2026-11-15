import { apiBaseUrl } from './config';
import { ApiError, type ApiList, type ApiSummary } from './types';

export interface PlumeApi {
  listApis(signal?: AbortSignal): Promise<ApiList>;
  getApi(id: string, signal?: AbortSignal): Promise<ApiSummary>;
}

/** Typed fetch client. The maintainer key, when present, is passed in by the caller (never stored here). */
export function createApiClient(
  baseUrl: string = apiBaseUrl(),
  opts: { maintainerKey?: () => string | null; fetchImpl?: typeof fetch } = {},
): PlumeApi {
  const doFetch = opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));

  async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    const key = opts.maintainerKey?.();
    if (key) headers.Authorization = `Bearer ${key}`;
    const res = await doFetch(`${baseUrl}${path}`, { headers, signal });
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

  return {
    listApis: (signal) => get<ApiList>('/v1/apis', signal),
    getApi: (id, signal) => get<ApiSummary>(`/v1/apis/${encodeURIComponent(id)}`, signal),
  };
}
