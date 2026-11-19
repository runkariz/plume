import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { server, TEST_API_BASE } from '@/test/server';
import { renderApp } from '@/test/render';

afterEach(() => authStore.signOut());

describe('Try it', () => {
  it('starts idle with the build chip and the three tools', async () => {
    renderApp('/apis/shopify/try');
    expect(await screen.findByText('Build 2026-11-14 · live')).toBeInTheDocument();
    expect(screen.getByText('Nothing run yet')).toBeInTheDocument();
    for (const name of ['Search', 'Ask', 'Check call'])
      expect(screen.getByRole('radio', { name })).toBeInTheDocument();
  });

  it('runs a search: ranked results, scores, trace and the Claude payload', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(
      await screen.findByText('Pagination: Link header, URL lifespan and range searches'),
    ).toBeInTheDocument();
    expect(screen.getByText('dense #1')).toBeInTheDocument();
    expect(screen.getByText('0.0325')).toBeInTheDocument();
    const trace = screen
      .getByRole('heading', { name: 'Query trace' })
      .closest('div') as HTMLElement;
    expect(within(trace).getByText('Embedded the question, 768 dims')).toBeInTheDocument();
    expect(within(trace).getByText('47 ms')).toBeInTheDocument();
    expect(screen.getByText(/"docs_as_of": "2026-11-14"/)).toBeInTheDocument();
  });

  it('kind filter narrows the request', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Guides' }));
    await userEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(await screen.findByText('REST Admin API request rate limits')).toBeInTheDocument();
    expect(screen.queryByText('Retrieve a list of orders')).not.toBeInTheDocument();
  });

  it('shows an empty result state', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/search`, () =>
        HttpResponse.json({
          api: 'shopify',
          docsAsOf: '2026-11-14',
          results: [],
          trace: [],
          totalMs: 1,
          claudePayload: '{}',
        }),
      ),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(await screen.findByText('No results')).toBeInTheDocument();
  });

  it('shows the loading state while running, then an error state', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/search`, () =>
        HttpResponse.json({ detail: 'embedder unavailable' }, { status: 502 }),
      ),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('embedder unavailable');
  });

  it('Ask returns the passages Claude would receive', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Ask' }));
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText(/Cursor-based pagination/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Source' })[0]).toHaveAttribute(
      'href',
      expect.stringContaining('shopify.dev'),
    );
  });

  it('Ask shows "not documented" when nothing matches', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/ask`, () =>
        HttpResponse.json({
          api: 'shopify',
          docsAsOf: '2026-11-14',
          question: 'x',
          passages: [],
          trace: [],
          totalMs: 1,
        }),
      ),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Ask' }));
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('Not documented in this build')).toBeInTheDocument();
  });

  it('Check call reports documented and per-parameter results', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    expect(await screen.findByText('Documented')).toBeInTheDocument();
    expect(screen.getAllByText('found')).toHaveLength(2);
  });

  it('Check call reports not documented with the wording rule and the partial warning', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/check-call`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: '2026-11-14',
          verdict: 'not_documented',
          complete: false,
          matched: null,
          paramChecks: [{ name: 'foo', found: false, where: null }],
          checked: { endpoints: 137, models: 31 },
        }),
      ),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    expect(await screen.findByText('Not documented in build 2026-11-14')).toBeInTheDocument();
    expect(screen.getByText('Schema partial: absence not proven')).toBeInTheDocument();
    expect(screen.getByText('missing')).toBeInTheDocument();
  });

  it('Check call sends only the keys the server accepts, and shows its note', async () => {
    let sent: Record<string, unknown> = {};
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/check-call`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          api: 'shopify',
          build: '2026-11-14',
          verdict: 'not_documented',
          complete: true,
          matched: null,
          paramChecks: [],
          checked: { endpoints: 1, models: 1 },
          note: 'the documented operation is GET /v4/orders',
        });
      }),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    const note = await screen.findByRole('note');
    expect(note).toHaveTextContent('the documented operation is GET /v4/orders');
    // the server answers 422 to any other key
    const allowed = ['method', 'path', 'params', 'query', 'body', 'version'];
    expect(Object.keys(sent).filter((k) => !allowed.includes(k))).toEqual([]);
    expect(Object.keys(sent)).toEqual(expect.arrayContaining(['method', 'path', 'params']));
  });

  it('Check call shows no note when the server sends none', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(screen.getByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    await screen.findByText('Documented');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('uses the public breadcrumb when signed out and the maintainer one when signed in', async () => {
    const { unmount } = renderApp('/apis/shopify/try');
    await screen.findByText('Build 2026-11-14 · live');
    expect(screen.getByRole('link', { name: 'APIs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Maintainer' })).toBeInTheDocument();
    unmount();
    authStore.signIn('k');
    renderApp('/apis/shopify/try');
    await screen.findByText('Build 2026-11-14 · live');
    expect(screen.getAllByText('Maintainer').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(authStore.getKey()).toBeNull();
  });

  it('shows not found for an unknown API', async () => {
    renderApp('/apis/nope/try');
    expect(await screen.findByRole('alert')).toHaveTextContent('API not found');
  });
});
