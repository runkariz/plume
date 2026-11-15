import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { authStore, SESSION_STORAGE_KEY } from './authStore';

/** What a page refresh does to the module: it starts again and reads sessionStorage. */
async function reloadedStore() {
  vi.resetModules();
  return (await import('./authStore')).authStore;
}

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe('the maintainer session', () => {
  it('survives a page refresh (it is kept in sessionStorage)', async () => {
    authStore.signIn('pl_secret_token_value', 'hamzeh', true);
    expect(JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY) ?? '{}')).toEqual({
      key: 'pl_secret_token_value',
      name: 'hamzeh',
      generation: true,
    });
    const fresh = await reloadedStore();
    expect(fresh.getKey()).toBe('pl_secret_token_value');
    expect(fresh.getName()).toBe('hamzeh');
    fresh.signOut();
  });

  it('is never in localStorage, the URL or the console', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    authStore.signIn('pl_secret_token_value');
    expect(JSON.stringify({ ...localStorage })).not.toContain('pl_secret_token_value');
    expect(window.location.href).not.toContain('pl_secret_token_value');
    expect(JSON.stringify([...log.mock.calls, ...err.mock.calls])).not.toContain(
      'pl_secret_token_value',
    );
  });

  it('Sign out clears it, also after a refresh', async () => {
    authStore.signIn('pl_secret_token_value');
    authStore.signOut();
    expect(authStore.getKey()).toBeNull();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    expect((await reloadedStore()).getKey()).toBeNull();
  });

  it('a 401 clears it too', async () => {
    authStore.signIn('pl_secret_token_value');
    authStore.expire();
    expect(authStore.getKey()).toBeNull();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    authStore.expire(); // nothing to end: no second notice
  });

  it('ignores corrupt storage and starts signed out', async () => {
    for (const bad of ['{not json', '"text"', '{"key":""}', '{"key":1,"name":"x"}', '[]']) {
      sessionStorage.setItem(SESSION_STORAGE_KEY, bad);
      expect((await reloadedStore()).getKey(), bad).toBeNull();
    }
  });

  it('keeps working from memory when storage is blocked', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => authStore.signIn('pl_secret_token_value')).not.toThrow();
    expect(authStore.getKey()).toBe('pl_secret_token_value'); // in memory
    expect(() => authStore.signOut()).not.toThrow();
    expect(authStore.getKey()).toBeNull();
    expect((await reloadedStore()).getKey()).toBeNull(); // nothing to restore
  });
});

describe('in the app', () => {
  it('a refreshed page is still signed in (the Maintainer page opens without the sign-in form)', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer');
    expect(await screen.findByText('maintainer', { selector: '.user span' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Access token')).not.toBeInTheDocument();
  });

  it('signing in through the form keeps the session for the tab', async () => {
    renderApp('/maintainer');
    await userEvent.type(await screen.findByLabelText('Access token'), 'pl_form_token_value');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(authStore.getKey()).toBe('pl_form_token_value'));
    expect(JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY) ?? '{}').key).toBe(
      'pl_form_token_value',
    );
  });

  it('a refused token ends the session and returns to sign-in with the reason', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models`, () =>
        HttpResponse.json({ error: 'unauthorized', message: 'no' }, { status: 401 }),
      ),
    );
    authStore.signIn('pl_stale_token_value', 'maintainer'); // from an earlier visit; the server forgot it
    renderApp('/models'); // "Waiting for review" asks the API with the token
    expect(await screen.findByRole('alert')).toHaveTextContent('Your session ended');
    expect(await screen.findByLabelText('Access token')).toBeInTheDocument();
    expect(authStore.getKey()).toBeNull();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('a wrong token typed at sign-in is just "not accepted": no session ends, no expired notice', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/maintainer/me`, () =>
        HttpResponse.json({ error: 'unauthorized', message: 'no' }, { status: 401 }),
      ),
    );
    renderApp('/maintainer');
    await userEvent.type(await screen.findByLabelText('Access token'), 'pl_wrong_token_value');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('That token was not accepted.')).toBeInTheDocument();
    expect(screen.queryByText(/Your session ended/)).not.toBeInTheDocument();
    expect(authStore.getKey()).toBeNull();
  });

  it('Sign out clears the session', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/');
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(authStore.getKey()).toBeNull();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });
});
