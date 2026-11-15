import { useSyncExternalStore } from 'react';

/**
 * The maintainer key lives in memory only (never localStorage). A page reload signs the person out;
 * that is intended: the key is typed at sign-in and not persisted anywhere.
 */
let key: string | null = null;
const listeners = new Set<() => void>();

export const authStore = {
  getKey: () => key,
  signIn(next: string) {
    key = next;
    listeners.forEach((l) => l());
  },
  signOut() {
    key = null;
    listeners.forEach((l) => l());
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

export function useIsMaintainer(): boolean {
  return useSyncExternalStore(authStore.subscribe, () => authStore.getKey() !== null);
}
