import { render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { installChunkReload, isChunkLoadError, RELOAD_WINDOW_MS, reloadOnce } from './chunkReload';
import { RouteError } from './RouteError';

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
  };
}

describe('reloadOnce', () => {
  it('reloads the first time and remembers when', () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadOnce({ storage, reload, now: () => 1_000_000 })).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(storage.data['plume-chunk-reload-at']).toBe('1000000');
  });

  it('does not reload again within a minute (no reload loop when a chunk is really missing)', () => {
    const storage = memoryStorage({ 'plume-chunk-reload-at': '1000000' });
    const reload = vi.fn();
    expect(reloadOnce({ storage, reload, now: () => 1_000_000 + RELOAD_WINDOW_MS - 1 })).toBe(
      false,
    );
    expect(reload).not.toHaveBeenCalled();
  });

  it('reloads again once the minute has passed', () => {
    const storage = memoryStorage({ 'plume-chunk-reload-at': '1000000' });
    const reload = vi.fn();
    expect(reloadOnce({ storage, reload, now: () => 1_000_000 + RELOAD_WINDOW_MS })).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does not reload when storage is blocked: without the guard it could loop', () => {
    const storage = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => undefined,
    };
    const reload = vi.fn();
    expect(reloadOnce({ storage, reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('isChunkLoadError', () => {
  it.each([
    'Failed to fetch dynamically imported module: https://x/assets/ModelView-C8ptjjPq.js',
    'error loading dynamically imported module',
    'Importing a module script failed.',
    'Unable to preload CSS for /assets/x.css',
  ])('recognises "%s"', (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
  });

  it('does not take other errors for a stale build', () => {
    expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError({ status: 404 })).toBe(false);
  });
});

describe('installChunkReload', () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('on vite:preloadError reloads once and swallows the event; the second one is left alone', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    let handler: (e: Event) => void = () => undefined;
    installChunkReload({
      addEventListener: ((type: string, h: (e: Event) => void) => {
        if (type === 'vite:preloadError') handler = h;
      }) as Window['addEventListener'],
    });
    const first = new Event('vite:preloadError', { cancelable: true });
    handler(first);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(first.defaultPrevented).toBe(true);
    const second = new Event('vite:preloadError', { cancelable: true });
    handler(second);
    expect(reload).toHaveBeenCalledTimes(1); // guarded: it reaches the error page instead
    expect(second.defaultPrevented).toBe(false);
  });
});

function renderFailing(error: Error) {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        errorElement: <RouteError />,
        loader: () => {
          throw error;
        },
        element: <p>never shown</p>,
      },
    ],
    { initialEntries: ['/'] },
  );
  return render(<RouterProvider router={router} />);
}

describe('the error page', () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('says something went wrong, with Reload, Home and the details behind a disclosure', async () => {
    renderFailing(new Error('boom in a page'));
    const alert = await screen.findByRole('alert');
    expect(
      within(alert).getByRole('heading', { name: 'Something went wrong' }),
    ).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    expect(within(alert).getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(within(alert).getByText('boom in a page')).toBeInTheDocument();
    expect(screen.queryByText(/Unexpected Application Error/)).not.toBeInTheDocument();
    // a plain error never reloads the page by itself
    expect(sessionStorage.getItem('plume-chunk-reload-at')).toBeNull();
  });

  it('a stale chunk reloads once by itself; if it fails again the page says a new version is out', async () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    const chunk = new TypeError(
      'Failed to fetch dynamically imported module: https://x/assets/ModelView-C8ptjjPq.js',
    );
    const { unmount } = renderFailing(chunk);
    expect(
      await screen.findByRole('heading', { name: 'A new version of Plume is available' }),
    ).toBeInTheDocument();
    expect(reload).toHaveBeenCalledTimes(1);
    unmount();
    // the page came back and failed again: no second reload, the message stays for the person to act on
    renderFailing(chunk);
    expect(
      await screen.findByRole('heading', { name: 'A new version of Plume is available' }),
    ).toBeInTheDocument();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
