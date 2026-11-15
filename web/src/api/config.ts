/**
 * The API base URL comes from the environment only: there is no hard-coded default, so a missing variable is an
 * error. An EMPTY value (or "/") is a choice: the web and the API share an origin (a reverse proxy sends /v1 to the
 * API, the recommended deploy), and every call is a relative `/v1/...` request. An absolute URL still works (dev).
 */
export function apiBaseUrl(env: Record<string, unknown> = import.meta.env): string {
  const raw = env.VITE_API_BASE_URL;
  if (typeof raw !== 'string') {
    throw new Error(
      'VITE_API_BASE_URL is not set. Copy web/.env.example to web/.env.local (an empty value means the same origin).',
    );
  }
  return raw.trim().replace(/\/+$/, '');
}

export function mocksEnabled(env: Record<string, unknown> = import.meta.env): boolean {
  return env.VITE_USE_MOCKS === 'true';
}
