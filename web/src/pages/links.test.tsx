import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { endpointOfId, schemeIdOf } from '@/lib/docHref';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

const ep = encodeURIComponent('endpoint:GET~/orders.json');
const guide = encodeURIComponent('guide:pagination');

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('reading an endpoint id', () => {
  it('gives the method, the path and the operation', () => {
    expect(endpointOfId('endpoint:GET~/orders.json')).toEqual({
      method: 'GET',
      path: '/orders.json',
      operation: null,
    });
    expect(endpointOfId('endpoint:GET~/{file_path}@get-or15')).toEqual({
      method: 'GET',
      path: '/{file_path}',
      operation: 'get-or15',
    });
    expect(endpointOfId('endpoint:GET~/@scope/x')?.operation).toBeNull();
    expect(endpointOfId('guide:pagination')).toBeNull();
    expect(schemeIdOf('auth:oauth2')).toBe('oauth2');
    expect(schemeIdOf('oauth2')).toBe('oauth2');
  });
});

describe('endpoint page', () => {
  it('lists the required scopes per auth scheme, linked to the scheme, and the related guides', async () => {
    renderApp(`/apis/shopify/documents/${ep}`);
    const scopes = await screen.findByRole('region', { name: 'Required scopes' });
    expect(within(scopes).getByText('read_orders')).toBeInTheDocument();
    expect(within(scopes).getByRole('link', { name: 'oauth2-authorization-code' })).toHaveAttribute(
      'href',
      '/apis/shopify/auth/oauth2-authorization-code',
    );
    const guides = await screen.findByRole('region', { name: 'Related guides' });
    // the guide's own title replaces its id once it arrives
    const link = await within(guides).findByRole('link', {
      name: /Pagination: Link header|pagination/i,
    });
    expect(link).toHaveAttribute('href', `/apis/shopify/documents/${guide}`);
    expect(within(guides).getAllByRole('link')).toHaveLength(2);
  });

  it('shows nothing extra when the server sends no links', async () => {
    renderApp(`/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/products.json')}`);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: 'Related guides' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Required scopes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'About these endpoints' })).not.toBeInTheDocument();
  });

  it('a scope without a named scheme says so and links nowhere', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/documents/*`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: 'b',
          docsAsOf: '2026-11-14',
          id: 'endpoint:GET~/x',
          kind: 'endpoint',
          title: 'X',
          resource: null,
          method: 'GET',
          path: '/x',
          deprecated: false,
          complete: true,
          sourceUrl: null,
          anchor: null,
          text: 't',
          fields: [],
          scopes: ['a', 'b'],
          requiredScopes: [{ authId: null, scopes: ['a', 'b'] }],
        }),
      ),
    );
    renderApp('/apis/shopify/documents/endpoint%3AGET~%2Fx');
    const scopes = await screen.findByRole('region', { name: 'Required scopes' });
    expect(scopes).toHaveTextContent('Any scheme');
    expect(within(scopes).queryByRole('link')).not.toBeInTheDocument();
    expect(within(scopes).getByText('a')).toBeInTheDocument();
    // the flat list is not shown a second time
    expect(screen.queryByRole('region', { name: 'Scopes' })).not.toBeInTheDocument();
  });
});

describe('guide page', () => {
  it('says which endpoints it is about, as links', async () => {
    renderApp(`/apis/shopify/documents/${guide}`);
    const card = await screen.findByRole('region', { name: 'About these endpoints' });
    const links = within(card).getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', `/apis/shopify/documents/${ep}`);
    expect(links[0]).toHaveTextContent('GET');
    expect(links[0]).toHaveTextContent('/orders.json');
  });
});

describe('auth scheme page', () => {
  it('shows each scope with the endpoints that need it, long lists collapsed', async () => {
    renderApp('/apis/shopify/auth/oauth2-authorization-code');
    const card = await screen.findByRole('region', { name: 'Scopes' });
    expect(
      within(card).getByRole('columnheader', { name: 'Endpoints that need it' }),
    ).toBeVisible();
    const read = within(card).getByRole('list', { name: 'Endpoints that need read_orders' });
    expect(within(read).getAllByRole('link')).toHaveLength(3);
    await userEvent.click(within(card).getByRole('button', { name: 'Show all 5' }));
    expect(within(read).getAllByRole('link')).toHaveLength(5);
    // three endpoints: all shown, no button for them
    const write = within(card).getByRole('list', { name: 'Endpoints that need write_orders' });
    expect(within(write).getAllByRole('link')).toHaveLength(3);
  });

  it('has no endpoints column when the server sends none', async () => {
    renderApp('/apis/stripe/auth/api-key');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('columnheader', { name: 'Endpoints that need it' })).toBeNull();
  });
});
