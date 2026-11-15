import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server, TEST_API_BASE } from '@/test/server';
import { renderApp } from '@/test/render';

describe('API detail', () => {
  it('shows a loading state, then title, stats, quality, index and connect', async () => {
    renderApp('/apis/shopify');
    expect(screen.getByRole('status')).toHaveTextContent('Loading API');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByText('latest · docs as of 14 Nov 2026')).toBeInTheDocument();
    expect(screen.getByText('409')).toBeInTheDocument();
    expect(screen.getByText('Searchable chunks')).toBeInTheDocument();
    expect(screen.getByText('0.94')).toBeInTheDocument();
    expect(screen.getByText('0 / 40')).toBeInTheDocument();
    expect(screen.getByText('gemini-embedding-001')).toBeInTheDocument();
    expect(screen.getByText(/claude mcp add --transport http plume/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Try it/ })).toHaveAttribute(
      'href',
      '/apis/shopify/try',
    );
  });

  it('shows only what the server measured: no invented-endpoints row when it is null', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id`, async () => {
        const { shopifyDetail } = await import('@/mocks/data');
        return HttpResponse.json({
          ...shopifyDetail,
          quality: {
            ...shopifyDetail.quality,
            inventedEndpoints: null,
            citationHitRate: 0.88,
            factAccuracy: 0.9,
            missingExpected: 2,
          },
        });
      }),
    );
    renderApp('/apis/shopify');
    expect(await screen.findByText('Citation hit rate')).toBeInTheDocument();
    expect(screen.getByText('0.88')).toBeInTheDocument();
    expect(screen.getByText('Fact accuracy')).toBeInTheDocument();
    expect(screen.getByText('Expected docs missing')).toBeInTheDocument();
    expect(screen.queryByText('Invented endpoints')).not.toBeInTheDocument();
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it('explains a large model count: names as the number, files and structures as the hint', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id`, async () => {
        const { shopifyDetail } = await import('@/mocks/data');
        return HttpResponse.json({
          ...shopifyDetail,
          models: 1343,
          modelNames: 319,
          modelShapes: 717,
        });
      }),
    );
    renderApp('/apis/shopify');
    expect(await screen.findByText('319')).toBeInTheDocument();
    expect(screen.getByText('1343 model files · 717 structures')).toBeInTheDocument();
  });

  it('breadcrumb links back to the list', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('link', { name: 'APIs' })).toHaveAttribute('href', '/');
  });

  it('browses endpoints with method badges and filters them', async () => {
    renderApp('/apis/shopify');
    expect(
      (await screen.findAllByText('/admin/api/latest/orders.json', { selector: 'a' })).length,
    ).toBe(2);
    await userEvent.click(screen.getByRole('radio', { name: 'Guides' }));
    expect(await screen.findByText('REST Admin API request rate limits')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.type(screen.getByRole('searchbox', { name: /Filter by path/ }), 'customers');
    expect(await screen.findByText('Retrieve a single customer')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Create an order')).not.toBeInTheDocument());
  });

  it('every Browse item links to its detail page (endpoints, models, guides)', async () => {
    renderApp('/apis/shopify');
    await screen.findAllByText('Retrieve a list of orders');
    const hrefs = [...document.querySelectorAll('.ep-link')].map((a) => a.getAttribute('href'));
    expect(hrefs.length).toBeGreaterThanOrEqual(9);
    expect(hrefs.every((h) => h?.startsWith('/apis/shopify/documents/'))).toBe(true);
    expect(hrefs).toContain(`/apis/shopify/documents/${encodeURIComponent('endpoint:get-orders')}`);
    // models and guides too
    await userEvent.click(screen.getByRole('radio', { name: 'Models' }));
    const browse = within(document.querySelector('.browse') as HTMLElement);
    const model = await browse.findByRole('link', { name: 'Order' });
    expect(model).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('model:order')}`,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Guides' }));
    const guide = await browse.findByRole('link', { name: 'REST Admin API request rate limits' });
    expect(guide).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('guide:rate-limits')}`,
    );
  });

  it('opening an endpoint shows its detail: method, path, grouped parameters, responses, source JSON', async () => {
    renderApp('/apis/shopify');
    const link = (await screen.findAllByRole('link', { name: '/admin/api/latest/orders.json' }))[1];
    expect(link).toBeTruthy();
    await userEvent.click(link as HTMLElement);
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    for (const name of ['Query parameters', 'Headers', 'Request body', 'Response fields'])
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    expect(screen.getByText('order.total')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Responses' })).toHaveTextContent('No such order.');
    expect(screen.getByText('Source JSON, as in the package')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Shopify Admin REST API' })).toHaveAttribute(
      'href',
      '/apis/shopify',
    );
  });

  it('shows the empty state when the filter matches nothing', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1 });
    await userEvent.type(screen.getByRole('searchbox', { name: /Filter by path/ }), 'qqqq');
    expect(await screen.findByText('Nothing matches')).toBeInTheDocument();
  });

  it('shows an error state for the browse list and retries', async () => {
    server.use(
      http.get(
        `${TEST_API_BASE}/v1/apis/:id/items`,
        () => HttpResponse.json({ detail: 'index offline' }, { status: 500 }),
        {
          once: true,
        },
      ),
    );
    renderApp('/apis/shopify');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('index offline');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Retrieve a list of orders')).toBeInTheDocument();
  });

  it('shows not found for an unknown API', async () => {
    renderApp('/apis/nope');
    expect(await screen.findByRole('alert')).toHaveTextContent('API not found');
  });

  it('shows a generic error when the API call fails', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderApp('/apis/shopify');
    expect(await screen.findByText('Could not load this API')).toBeInTheDocument();
  });
});
