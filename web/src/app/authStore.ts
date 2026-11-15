import { useSyncExternalStore } from 'react';

/**
 * The maintainer key lives in memory only (never localStorage or sessionStorage). A page reload
 * signs the person out; that is intended: the key is typed at sign-in and not persisted anywhere.
 */
interface Session {
  key: string;
  name: string;
  /** null = the server did not say */
  generation: boolean | null;
}

let session: Session | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const authStore = {
  getKey: () => session?.key ?? null,
  getName: () => session?.name ?? null,
  signIn(key: string, name = 'maintainer', generation: boolean | null = null) {
    session = { key, name, generation };
    emit();
  },
  signOut() {
    session = null;
    emit();
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

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
