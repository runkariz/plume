import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('rate limits', () => {
  it('shows the numbers of a group, the algorithm and the headers on the API page', async () => {
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Rate limits' });
    expect(card).toHaveTextContent('app');
    expect(card).toHaveTextContent('rest-admin');
    expect(card).toHaveTextContent('40 per 20 s');
    expect(card).toHaveTextContent('leaky-bucket');
    expect(within(card).getByText('X-Shopify-Shop-Api-Call-Limit')).toBeInTheDocument();
  });

  it('shows only what the package says when there are no numbers', async () => {
    renderApp('/apis/amazon-sp-vendor');
    const card = await screen.findByRole('region', { name: 'Rate limits' });
    expect(card).toHaveTextContent('endpoint-group');
    expect(card).toHaveTextContent('leaky-bucket');
    expect(card).toHaveTextContent('Each operation has its own rate and burst.');
    expect(card).not.toHaveTextContent(/per \d+ s/);
  });

  it('shows no card for an API without rate limits', async () => {
    renderApp('/apis/stripe');
    await screen.findByRole('heading', { level: 1, name: 'Stripe API' });
    expect(screen.queryByRole('region', { name: 'Rate limits' })).not.toBeInTheDocument();
  });

  it('shows the limit of an endpoint: bucket, cost and group numbers', async () => {
    renderApp('/apis/amazon-sp-vendor/documents/endpoint:get-orders');
    const card = await screen.findByRole('region', { name: 'Rate limit' });
    expect(card).toHaveTextContent('orders');
    expect(card).toHaveTextContent('Cost per call');
    expect(card).toHaveTextContent('purchase-orders');
    expect(card).toHaveTextContent('10 per 60 s');
  });

  it('shows no card for an endpoint with a null limit', async () => {
    renderApp('/apis/shopify/documents/endpoint:get-orders');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: 'Rate limit' })).not.toBeInTheDocument();
  });
});

describe('the real path', () => {
  it('Browse and the document show the vendor path when there is one, the package path when not', async () => {
    renderApp('/apis/amazon-sp-vendor');
    const first = await screen.findAllByRole('link', { name: /^\/vendor\/orders\/v1/ });
    expect(first.length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /^\/admin\/api/ })).not.toBeInTheDocument();
  });

  it('Shopify (no real path) keeps showing its own path', async () => {
    renderApp('/apis/shopify');
    expect((await screen.findAllByRole('link', { name: /\/admin\/api\// })).length).toBeGreaterThan(
      0,
    );
  });

  it('the document page shows the real path and keeps the package path in its title', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/documents/endpoint:get-orders`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          docsAsOf: '2026-11-14',
          id: 'endpoint:get-orders',
          kind: 'endpoint',
          title: 'List orders',
          resource: null,
          method: 'GET',
          path: '/orders',
          realPath: '/vendor/orders/v1/purchaseOrders',
          versionFixed: true,
          rateLimit: null,
          deprecated: false,
          complete: true,
          sourceUrl: null,
          anchor: null,
          text: 'x',
          fields: [],
          scopes: [],
        }),
      ),
    );
    renderApp('/apis/shopify/documents/endpoint:get-orders');
    const path = await screen.findByText('/vendor/orders/v1/purchaseOrders');
    expect(path).toHaveAttribute('title', 'Package path: /orders');
  });
});

describe('field constraints', () => {
  it('shows the allowed values under the description, as text', async () => {
    renderApp('/apis/shopify/documents/endpoint:get-orders');
    const table = await screen.findByRole('region', { name: 'Query parameters' });
    const limit = within(table).getByRole('row', { name: /limit/ });
    expect(limit).toHaveTextContent('value 1–250');
    expect(limit).toHaveTextContent('default 50');
    const status = within(table).getByRole('row', { name: /status/ });
    expect(status).toHaveTextContent('one of open | closed | cancelled');
  });

  it('a field without constraints shows none', async () => {
    renderApp('/apis/shopify/documents/endpoint:get-orders');
    const table = await screen.findByRole('region', { name: 'Headers' });
    expect(within(table).queryByLabelText('Constraints')).not.toBeInTheDocument();
  });
});
