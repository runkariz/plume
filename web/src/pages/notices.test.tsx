import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { warningText } from '@/components/Notices';
import { shopifyDetail } from '@/mocks/data';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('notices', () => {
  it('the auth section shows the package notice as a note, not an alert', async () => {
    renderApp('/apis/stripe?section=auth');
    const list = await screen.findByRole('list', { name: 'Notes on this package' });
    expect(list).toHaveTextContent('Every request must be signed');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // the schemes are still listed under it
    expect(screen.getByRole('link', { name: 'API key (secret key)' })).toBeInTheDocument();
  });

  it('a package with no auth scheme and a notice shows the note and the empty state', async () => {
    const auth = {
      api: 'stripe',
      build: 'b',
      present: false,
      note: 'not in this package',
      schemes: [],
      notices: [{ code: 'auth-requires-signature', section: 'auth', text: 'Sign every request.' }],
    };
    server.use(http.get(`${TEST_API_BASE}/v1/apis/stripe/auth`, () => HttpResponse.json(auth)));
    renderApp('/apis/stripe?section=auth');
    expect(await screen.findByText('Sign every request.')).toBeInTheDocument();
    expect(screen.getByText('Not in this package')).toBeInTheDocument();
  });

  it('the environments card shows its notice', async () => {
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    expect(within(card).getByRole('list', { name: 'Notes on this package' })).toHaveTextContent(
      'first one listed is used',
    );
  });

  it('an environments notice is shown even when the package lists no environment', async () => {
    const env = {
      api: 'shopify',
      build: 'b',
      present: false,
      note: 'not in this package',
      environments: [],
      versioning: null,
      baseUrls: null,
      variablesSchema: null,
      notices: [{ code: 'x', section: 'environments', text: 'Ask the vendor for the base URL.' }],
    };
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/environments`, () => HttpResponse.json(env)),
    );
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    expect(card).toHaveTextContent('Ask the vendor for the base URL.');
  });

  it('shows nothing when the server sends no notices', async () => {
    renderApp('/apis/shopify?section=auth');
    await screen.findByRole('link', { name: 'OAuth2 authorization code' });
    const auth = screen.getByRole('region', { name: 'Authentication' });
    expect(within(auth).queryByRole('list', { name: 'Notes on this package' })).toBeNull();
  });
});

describe('package warnings (maintainer view)', () => {
  it('are not shown to a reader', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByRole('region', { name: 'Package warnings' })).not.toBeInTheDocument();
  });

  it('a signed-in maintainer sees a code chip and the text, the code said once', async () => {
    authStore.signIn('pl_k');
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Package warnings' });
    expect(card).toHaveTextContent('Package warnings (5)');
    const items = within(card).getAllByRole('listitem');
    expect(items).toHaveLength(5);
    expect(items[1]).toHaveTextContent('knowledge-links');
    expect(items[1]).toHaveTextContent('3 units with endpointId');
    expect(items[1]?.textContent?.match(/knowledge-links/g)).toHaveLength(1);
  });

  it('sends the maintainer token on the API call, and none for a reader', async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify`, ({ request }) => {
        seen.push(request.headers.get('authorization'));
        return HttpResponse.json({ ...shopifyDetail });
      }),
    );
    const { unmount } = renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(seen).toEqual([null]);
    unmount();
    authStore.signIn('pl_k');
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(seen.at(-1)).toBe('Bearer pl_k');
  });

  it('a field the server leaves out (a reader) means no warnings', async () => {
    authStore.signIn('pl_k');
    const { packageWarnings: _omitted, ...without } = shopifyDetail;
    void _omitted;
    server.use(http.get(`${TEST_API_BASE}/v1/apis/shopify`, () => HttpResponse.json(without)));
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByRole('region', { name: 'Package warnings' })).not.toBeInTheDocument();
  });

  it('collapses a long list', async () => {
    authStore.signIn('pl_k');
    const many = Array.from({ length: 9 }, (_, i) => ({ code: `c${i}`, text: `c${i}: text ${i}` }));
    const base = (await (await fetch(`${TEST_API_BASE}/v1/apis/shopify`)).json()) as object;
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify`, () =>
        HttpResponse.json({ ...base, packageWarnings: many }),
      ),
    );
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Package warnings' });
    expect(within(card).getAllByRole('listitem')).toHaveLength(6);
    await userEvent.click(within(card).getByRole('button', { name: 'Show all 9' }));
    expect(within(card).getAllByRole('listitem')).toHaveLength(9);
  });

  it('no card for no warnings or an older server', async () => {
    authStore.signIn('pl_k');
    const base = (await (await fetch(`${TEST_API_BASE}/v1/apis/shopify`)).json()) as Record<
      string,
      unknown
    >;
    delete base.packageWarnings;
    server.use(http.get(`${TEST_API_BASE}/v1/apis/shopify`, () => HttpResponse.json(base)));
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByRole('region', { name: 'Package warnings' })).not.toBeInTheDocument();
  });

  it('only a leading "code:" is taken off the text', () => {
    expect(warningText({ code: 'a', text: 'a: b' })).toBe('b');
    expect(warningText({ code: 'a', text: 'about a: b' })).toBe('about a: b');
  });
});
