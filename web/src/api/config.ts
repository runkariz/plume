/** API base URL comes from the environment only: there is no hard-coded default. */
export function apiBaseUrl(env: Record<string, unknown> = import.meta.env): string {
  const raw = env.VITE_API_BASE_URL;
  if (typeof raw !== 'string' || raw.trim() === '') {
    throw new Error('VITE_API_BASE_URL is not set. Copy web/.env.example to web/.env.local.');
  }
  return raw.trim().replace(/\/+$/, '');
}

export function mocksEnabled(env: Record<string, unknown> = import.meta.env): boolean {
  return env.VITE_USE_MOCKS === 'true';
}
