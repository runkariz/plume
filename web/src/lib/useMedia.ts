import { useSyncExternalStore } from 'react';

/** Whether a media query matches, known on the first render (no measuring, so nothing flickers or re-fits). */
export function useMedia(query: string, fallback: boolean): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia?.(query);
      m?.addEventListener('change', cb);
      return () => m?.removeEventListener('change', cb);
    },
    () => window.matchMedia?.(query).matches ?? fallback,
    () => fallback,
  );
}
