/**
 * Owner keys: when someone without a maintainer token creates a model, the server returns an `ownerKey` once. It
 * only lists "my models" (POST /v1/models/mine); the model's link works without it. The keys live in this
 * browser's localStorage, the maintainer token never does (see authStore). Storage can be unavailable (private
 * window, blocked data): everything here then quietly does nothing.
 */
const KEY = 'plume-owner-keys';

export function readOwnerKeys(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && x !== '') : [];
  } catch {
    return [];
  }
}

export function saveOwnerKey(key: string): void {
  if (!key) return;
  try {
    const keys = readOwnerKeys();
    if (!keys.includes(key)) localStorage.setItem(KEY, JSON.stringify([...keys, key]));
  } catch {
    /* storage unavailable */
  }
}

export function forgetOwnerKeys(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}

/** The link to a model: this site's origin plus the server's share path (the server may not know its public URL). */
export function shareLink(model: { id: string; sharePath?: string }): string {
  return `${window.location.origin}${model.sharePath ?? `/models/${model.id}`}`;
}
