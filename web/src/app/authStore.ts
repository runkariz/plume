import { useSyncExternalStore } from 'react';

/**
 * The maintainer key lives in memory only (never localStorage or sessionStorage). A page reload
 * signs the person out; that is intended: the key is typed at sign-in and not persisted anywhere.
 */
interface Session {
  key: string;
  name: string;
}

let session: Session | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const authStore = {
  getKey: () => session?.key ?? null,
  getName: () => session?.name ?? null,
  signIn(key: string, name = 'maintainer') {
    session = { key, name };
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
