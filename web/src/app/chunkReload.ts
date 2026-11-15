/**
 * After a deploy, a tab that still runs the previous build asks for lazy chunks (e.g. ModelView-<hash>.js) that no
 * longer exist, and the import fails. The fix for the person is a reload: it fetches the new index and its chunks.
 * It is done at most once per minute (sessionStorage), so a chunk that is really missing cannot cause a reload loop;
 * then the error page explains and offers Reload.
 */
const KEY = 'plume-chunk-reload-at';
export const RELOAD_WINDOW_MS = 60_000;

const CHUNK_ERROR =
  /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS|ChunkLoadError/i;

export function isChunkLoadError(error: unknown): boolean {
  const text =
    error instanceof Error
      ? `${error.name} ${error.message}`
      : typeof error === 'string'
        ? error
        : '';
  return CHUNK_ERROR.test(text);
}

interface Deps {
  storage?: Pick<Storage, 'getItem' | 'setItem'>;
  reload?: () => void;
  now?: () => number;
}

/** Reloads the page unless it already did within the last minute. Returns whether it reloaded. */
export function reloadOnce({
  storage,
  reload = () => window.location.reload(),
  now = Date.now,
}: Deps = {}): boolean {
  try {
    const store = storage ?? window.sessionStorage;
    const last = Number(store.getItem(KEY) ?? 0);
    if (last && now() - last < RELOAD_WINDOW_MS) return false;
    store.setItem(KEY, String(now()));
  } catch {
    return false; // storage blocked: without the guard a reload could loop, so do not reload
  }
  reload();
  return true;
}

/** Vite fires `vite:preloadError` when a lazy chunk or its CSS cannot be loaded. */
export function installChunkReload(target: Pick<Window, 'addEventListener'> = window): void {
  target.addEventListener('vite:preloadError', (event) => {
    // reloading: swallow the error; not allowed to reload (just did): let it reach the error page
    if (reloadOnce()) event.preventDefault();
  });
}
