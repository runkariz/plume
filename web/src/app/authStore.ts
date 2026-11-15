import { useSyncExternalStore } from 'react';

/**
 * The maintainer key: in memory, and in sessionStorage so that a page refresh (or a new page in the same tab) does
 * not sign the person out. It is gone when the tab closes, on Sign out, and when the API answers 401 to it.
 * It is never put in the URL, in localStorage or in a log. The price is that a script injected into the page
 * (XSS) could read sessionStorage, see docs/security.md; a public deployment should use an httpOnly cookie.
 * Storage can be blocked (private window, site data off): everything then works from memory only.
 */
interface Session {
  key: string;
  name: string;
  /** null = the server did not say */
  generation: boolean | null;
}

export const SESSION_STORAGE_KEY = 'plume-maintainer-session';

function restore(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const v: unknown = JSON.parse(raw);
    if (typeof v !== 'object' || v === null) return null;
    const s = v as Record<string, unknown>;
    if (typeof s.key !== 'string' || s.key === '' || typeof s.name !== 'string') return null;
    return {
      key: s.key,
      name: s.name,
      generation: typeof s.generation === 'boolean' ? s.generation : null,
    };
  } catch {
    return null; // blocked or corrupt: signed out
  }
}

function persist(s: Session | null) {
  try {
    if (s) sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(s));
    else sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    /* storage blocked: the session lives in memory only */
  }
}

let session: Session | null = restore();
/** How many times the API refused the key (the Layout then returns to sign-in with a message). */
let expired = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const authStore = {
  getKey: () => session?.key ?? null,
  getName: () => session?.name ?? null,
  signIn(key: string, name = 'maintainer', generation: boolean | null = null) {
    session = { key, name, generation };
    persist(session);
    emit();
  },
  signOut() {
    session = null;
    persist(null);
    emit();
  },
  /** The API answered 401 to the key we sent: it is not valid (any more). */
  expire() {
    if (!session) return;
    session = null;
    persist(null);
    expired += 1;
    emit();
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

/** Counts the sessions the API refused; changes when one ends that way. */
export function useSessionExpiries(): number {
  return useSyncExternalStore(authStore.subscribe, () => expired);
}

export function useIsMaintainer(): boolean {
  return useSyncExternalStore(authStore.subscribe, () => session !== null);
}

export function useMaintainerName(): string | null {
  return useSyncExternalStore(authStore.subscribe, () => session?.name ?? null);
}

/**
 * Whether server-side generation works: false when the server said it has no model key (then "Generate" goes
 * straight to Claude), true when it said it has, null when unknown (older server, or signed out).
 */
export function useServerGeneration(): boolean | null {
  return useSyncExternalStore(authStore.subscribe, () => session?.generation ?? null);
}
