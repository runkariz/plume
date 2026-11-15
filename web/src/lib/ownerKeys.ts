/**
 * Old owner keys: before "My models" links, the server handed a key to whoever saved a model without a token, and this
 * browser kept the keys in localStorage. They are read ONCE to switch to the link they became (POST /v1/models/mine
 * answers `collections`), then forgotten. Nothing writes a new key any more. Storage can be unavailable: this then
 * quietly does nothing.
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

export function forgetOwnerKeys(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}
