import { fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

describe('API page sections', () => {
  it('has Browse, Authentication and Triggers tabs with the package counts', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('radio', { name: 'Browse' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Authentication (1)' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Triggers (3)' })).toBeInTheDocument();
  });

  it('switching tabs keeps the choice in the URL, so a link opens the right section', async () => {
    renderApp('/apis/shopify?section=auth');
    expect(await screen.findByRole('region', { name: 'Authentication' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Authentication (1)' })).toBeChecked();
    await userEvent.click(screen.getByRole('radio', { name: 'Triggers (3)' }));
    expect(
      await screen.findByRole('region', { name: 'Triggers and webhooks' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Browse' }));
    expect(await screen.findByRole('heading', { name: 'Browse' })).toBeInTheDocument();
  });
});

describe('Authentication tab', () => {
  it('lists the schemes with type, grant, header and the scope and variable counts', async () => {
    renderApp('/apis/shopify?section=auth');
    const card = await screen.findByRole('region', { name: 'Authentication' });
    const link = await within(card).findByRole('link', { name: 'OAuth2 authorization code' });
    expect(link).toHaveAttribute('href', '/apis/shopify/auth/oauth2-authorization-code');
    expect(within(card).getByText('OAUTH2')).toBeInTheDocument();
    expect(within(card).getByText('authorization_code')).toBeInTheDocument();
    expect(within(card).getByText(/header X-Shopify-Access-Token/)).toBeInTheDocument();
    expect(within(card).getByText('15 scopes · 0 variables')).toBeInTheDocument();
  });

  it('says "Not in this package" when the package has no auth section (and invents nothing)', async () => {
    renderApp('/apis/github?section=auth');
    expect(await screen.findByText('Not in this package')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /OAuth|API key/ })).not.toBeInTheDocument();
  });

  it('shows an error state when the section cannot be loaded', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/auth`, () =>
        HttpResponse.json({ error: 'internal', message: 'auth index offline' }, { status: 500 }),
      ),
    );
    renderApp('/apis/shopify?section=auth');
    expect(await screen.findByRole('alert')).toHaveTextContent('auth index offline');
  });
});

describe('auth scheme page', () => {
  it('shows how it works, the setup steps, scopes (filterable) and the verbatim JSON, collapsed', async () => {
    renderApp('/apis/shopify/auth/oauth2-authorization-code');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'OAuth2 authorization code' }),
    ).toBeInTheDocument();
    const how = within(screen.getByRole('region', { name: 'How it works' }));
    expect(how.getByText('OAUTH2')).toBeInTheDocument();
    expect(how.getByText('authorization_code')).toBeInTheDocument();
    expect(how.getByText('X-Shopify-Access-Token')).toBeInTheDocument();
    expect(how.getByText(/Token lifetime: refreshBehavior/)).toBeInTheDocument();
    const steps = within(screen.getByRole('region', { name: 'Setup steps' })).getAllByRole(
      'listitem',
    );
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Redirect the merchant to Shopify's authorization page");
    // 15 scopes: a filter appears
    const scopes = screen.getByRole('region', { name: 'Scopes' });
    expect(within(scopes).getAllByRole('row')).toHaveLength(16);
    await userEvent.type(
      within(scopes).getByRole('searchbox', { name: 'Filter scopes' }),
      'inventory',
    );
    expect(within(scopes).getAllByRole('row')).toHaveLength(3);
    expect(within(scopes).getByText('2 of 15 scopes')).toBeInTheDocument();
    expect(
      screen.getByText('Scheme JSON, as in the package').closest('details'),
    ).not.toHaveAttribute('open');
    expect(screen.queryByText('Variables JSON Schema, as in the package')).not.toBeInTheDocument();
  });

  it('shows the variables a scheme needs and its variables schema', async () => {
    renderApp('/apis/stripe/auth/api-key');
    const vars = await screen.findByRole('region', { name: 'Variables' });
    expect(within(vars).getByText('api_key')).toBeInTheDocument();
    expect(within(vars).getByText('required')).toBeInTheDocument();
    expect(screen.getByText('Variables JSON Schema, as in the package')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Scopes' })).not.toBeInTheDocument(); // none in the package
    expect(screen.queryByRole('region', { name: 'Setup steps' })).not.toBeInTheDocument();
  });

  it('renders setup steps of other shapes verbatim instead of guessing', async () => {
    const { stepText } = await import('./AuthSchemePage');
    expect(stepText({ order: 2, text: 'Do this' })).toEqual({ order: 2, text: 'Do this' });
    expect(stepText('Plain step')).toEqual({ order: null, text: 'Plain step' });
    expect(stepText({ title: 'Titled' }).text).toBe('Titled');
    expect(stepText({ weird: [1, 2] }).text).toBe('{"weird":[1,2]}');
  });

  it('shows not found and errors', async () => {
    const { unmount } = renderApp('/apis/shopify/auth/nope');
    expect(await screen.findByRole('alert')).toHaveTextContent('Authentication scheme not found');
    unmount();
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/auth/:scheme`, () =>
        HttpResponse.json({ error: 'internal', message: 'index offline' }, { status: 500 }),
      ),
    );
    renderApp('/apis/shopify/auth/oauth2-authorization-code');
    expect(await screen.findByText('Could not load this scheme')).toBeInTheDocument();
  });
});

describe('Triggers tab', () => {
  it('lists the events with resource and delivery, linking each to its page (the key is URL-encoded)', async () => {
    renderApp('/apis/shopify?section=triggers');
    const card = await screen.findByRole('region', { name: 'Triggers and webhooks' });
    const link = await within(card).findByRole('link', { name: 'app/scopes_update' });
    expect(link).toHaveAttribute('href', '/apis/shopify/triggers/app%2Fscopes_update');
    expect(within(card).getByText(/Occurs whenever the access scopes/)).toBeInTheDocument();
    expect(within(card).getAllByText('webhook')).toHaveLength(3);
    expect(within(card).getByText('3 of 3 events')).toBeInTheDocument();
  });

  it('filters the loaded events', async () => {
    renderApp('/apis/shopify?section=triggers');
    await screen.findByRole('link', { name: 'orders/create' });
    await userEvent.type(screen.getByRole('searchbox', { name: 'Filter events' }), 'uninstalled');
    expect(screen.getByText('1 of 3 events match')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'orders/create' })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole('searchbox', { name: 'Filter events' }), 'zzz');
    expect(screen.getByText('No event matches')).toBeInTheDocument();
  });

  it('shows a clear "Not in this package" when the package has no triggers or webhooks', async () => {
    renderApp('/apis/stripe?section=triggers');
    const card = await screen.findByRole('region', { name: 'Triggers and webhooks' });
    expect(await within(card).findByText('Not in this package')).toBeInTheDocument();
    expect(
      within(card).getByText(/The package has no triggers or webhooks \(not in this package\)/),
    ).toBeInTheDocument();
    expect(within(card).queryByRole('searchbox')).not.toBeInTheDocument();
  });

  it('loads more events page by page', async () => {
    const events = Array.from({ length: 120 }, (_, i) => ({
      key: `topic/event_${i}`,
      docId: `trigger:topic-event_${i}`,
      title: `topic/event_${i}`,
      description: null,
      resource: null,
      delivery: 'webhook',
    }));
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, ({ request }) => {
        const u = new URL(request.url);
        const limit = Number(u.searchParams.get('limit') ?? 50);
        const offset = Number(u.searchParams.get('offset') ?? 0);
        return HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          present: true,
          note: null,
          total: 120,
          items: events.slice(offset, offset + limit),
        });
      }),
    );
    renderApp('/apis/shopify?section=triggers');
    await screen.findByRole('link', { name: 'topic/event_0' });
    expect(screen.getByText('50 of 120 events')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show more (70 left)' }));
    expect(await screen.findByText('100 of 120 events')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show more (20 left)' }));
    expect(await screen.findByText('120 of 120 events')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Show more/ })).not.toBeInTheDocument();
  });
});

describe('trigger page', () => {
  it('shows what the event is, with the verbatim event JSON open and the vendor link', async () => {
    renderApp('/apis/shopify/triggers/app%2Fscopes_update');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'app/scopes_update' }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'Event' })).getByText(
        /Occurs whenever the access scopes/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the vendor page' })).toHaveAttribute(
      'rel',
      'noreferrer',
    );
    expect(screen.getByText('Event JSON, as in the package').closest('details')).toHaveAttribute(
      'open',
    );
    expect(screen.getByLabelText('Event JSON')).toHaveTextContent('"delivery": "webhook"');
    expect(screen.getByRole('link', { name: 'Back to Shopify Admin REST API' })).toHaveAttribute(
      'href',
      '/apis/shopify?section=triggers',
    );
  });

  it('says so when the package gives no description for the event', async () => {
    renderApp('/apis/shopify/triggers/app%2Funinstalled');
    expect(
      await screen.findByText('The package gives no description for this event.'),
    ).toBeInTheDocument();
  });

  it('shows not found', async () => {
    renderApp('/apis/shopify/triggers/nope%2Fnone');
    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found');
  });
});

describe('Environments card', () => {
  it('shows the environments and the versioning from the package', async () => {
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    expect(within(card).getByText('production', { selector: 'b' })).toBeInTheDocument();
    expect(within(card).getByText('default')).toBeInTheDocument();
    expect(within(card).getByText('https://{{app_env.vars.host}}')).toBeInTheDocument();
    expect(within(card).getByText(/API versions \(path\)/)).toBeInTheDocument();
    // the current version is said once, the others follow
    expect(within(card).getByText(/current/).textContent).toBe(
      'API versions (path): current 2026-10 · also 2026-07',
    );
    expect(within(card).getAllByText('2026-10')).toHaveLength(1);
  });

  it('renders nothing when the package has no environments (no empty state)', async () => {
    renderApp('/apis/stripe');
    await screen.findByRole('heading', { level: 1 });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole('region', { name: 'Environments' })).not.toBeInTheDocument();
  });
});

describe('Environments versions', () => {
  it('does not repeat the current version when it is the only one', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/environments`, async () => {
        const { environmentsFor } = await import('@/mocks/sectionData');
        const e = environmentsFor('shopify');
        return HttpResponse.json({
          ...e,
          versioning: { format: 'date', scheme: 'path', current: '2026-10', versions: ['2026-10'] },
        });
      }),
    );
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    expect(within(card).getByText(/API versions/).textContent).toBe(
      'API versions (path): current 2026-10',
    );
  });
});

describe('the package icon', () => {
  it('shows the package icon from the API on the card and the header, never an external URL', async () => {
    renderApp('/');
    const card = (await screen.findByRole('link', { name: 'Shopify Admin REST' })).closest(
      'article',
    ) as HTMLElement;
    const img = card.querySelector('img') as HTMLImageElement;
    expect(img.getAttribute('src')).toBe('http://api.test/v1/apis/shopify/icon');
    expect(img).toHaveAttribute('alt', '');
    // the image box has a pixel padding (a percentage would be relative to the card and collapse the image)
    expect((img.parentElement as HTMLElement).style.padding).toMatch(/^\d+px$/);
    expect(img).toHaveAttribute('referrerpolicy', 'no-referrer');
    // an API without an icon keeps the letter tile
    const stripe = (await screen.findByRole('link', { name: 'Stripe API' })).closest(
      'article',
    ) as HTMLElement;
    expect(stripe.querySelector('img')).toBeNull();
    expect(within(stripe).getByText('St')).toBeInTheDocument();
  });

  it('falls back to the letter tile when the icon cannot be loaded', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1 });
    const header = document.querySelector('.title-left') as HTMLElement;
    const img = header.querySelector('img') as HTMLImageElement;
    expect(img).toBeTruthy();
    fireEvent.error(img);
    expect(header.querySelector('img')).toBeNull();
    expect(within(header).getByText('S')).toBeInTheDocument();
  });

  it('ignores an external logo URL from a server that still sends one', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis`, async () => {
        const { sampleApis } = await import('@/mocks/data');
        const [first, ...rest] = sampleApis;
        return HttpResponse.json({
          items: [
            { ...first, logo: { ...first?.logo, url: 'https://shopify.dev/favicon.ico' } },
            ...rest,
          ],
        });
      }),
    );
    renderApp('/');
    const card = (await screen.findByRole('link', { name: 'Shopify Admin REST' })).closest(
      'article',
    ) as HTMLElement;
    expect(card.querySelector('img')).toBeNull();
  });
});

describe('webhook delivery mechanism', () => {
  it('shows how events are delivered, as the package states it', async () => {
    renderApp('/apis/shopify?section=triggers');
    const card = await screen.findByRole('region', { name: 'Webhook delivery' });
    expect(within(card).getByText('mode: api')).toBeInTheDocument();
    expect(within(card).getByText('handshake: none')).toBeInTheDocument();
    expect(within(card).getByText('Callback URL')).toBeInTheDocument();
    expect(within(card).getByText('in body at /webhook/address')).toBeInTheDocument();
    expect(within(card).getByText('in body at /webhook/topic (array)')).toBeInTheDocument();
    // unsubscribe is not in this build: the raw id stays, with the id variable beside it
    expect(
      within(card).getByText('delete-admin-api-latest-webhooks-webhook-id-json-2026-10'),
    ).toBeInTheDocument();
    expect(within(card).getByText(/id variable webhook_id/)).toBeInTheDocument();
    // the stream ids are resolved by the API: the subscribe endpoint shows METHOD + path as a link to its page,
    // the ones that are not in this build keep their raw id, marked
    const subscribe = within(within(card).getByText('Subscribe').closest('div') as HTMLElement);
    expect(subscribe.getByText('POST')).toBeInTheDocument();
    expect(subscribe.getByRole('link', { name: '/admin/api/latest/orders.json' })).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('endpoint:create-order')}`,
    );
    expect(within(card).getByText('get-admin-api-latest-webhooks-json')).toBeInTheDocument();
    expect(within(card).getAllByText('(not in this build)')).toHaveLength(2);
    // the events available and the evidence stay collapsed
    expect(within(card).getByText('events available').closest('details')).not.toHaveAttribute(
      'open',
    );
    expect(
      within(card).getByText('Where the docs say this').closest('details'),
    ).not.toHaveAttribute('open');
    expect(within(card).getByText('Mechanism JSON, as in the package')).toBeInTheDocument();
  });

  it('says only what is documented: a package with events but no mechanism shows none', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          present: true,
          note: null,
          total: 1,
          webhooks: [],
          items: [
            {
              key: 'a/b',
              docId: 'trigger:a-b',
              title: 'a/b',
              description: null,
              resource: null,
              delivery: null,
            },
          ],
        }),
      ),
    );
    renderApp('/apis/shopify?section=triggers');
    await screen.findByRole('link', { name: 'a/b' });
    expect(screen.queryByRole('region', { name: 'Webhook delivery' })).not.toBeInTheDocument();
  });

  it('a package with only the mechanism says no events are listed (not "not in this package")', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, async () => {
        const { SHOPIFY_WEBHOOK_MECHANISM } = await import('@/mocks/sectionData');
        return HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          present: true,
          note: null,
          total: 0,
          items: [],
          webhooks: [SHOPIFY_WEBHOOK_MECHANISM],
        });
      }),
    );
    renderApp('/apis/shopify?section=triggers');
    expect(await screen.findByText('No events listed')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Webhook delivery' })).toBeInTheDocument();
    expect(screen.queryByText('Not in this package')).not.toBeInTheDocument();
  });

  it('marks an event that is delivered by polling an endpoint', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          present: true,
          note: null,
          total: 1,
          webhooks: [],
          items: [
            {
              key: 'orders/poll',
              docId: 'trigger:orders-poll',
              title: 'orders/poll',
              description: null,
              resource: null,
              delivery: 'polling',
              syncEndpointId: 'get-orders',
            },
          ],
        }),
      ),
    );
    renderApp('/apis/shopify?section=triggers');
    const chip = await screen.findByText('polled');
    expect(chip.parentElement?.getAttribute('title')).toBe('get-orders');
  });
});

describe('webhook endpoint references', () => {
  it('an older server without endpointRefs shows the raw ids and no "not in this build" mark', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, async () => {
        const { triggersFor } = await import('@/mocks/sectionData');
        const { endpointRefs, ...rest } = triggersFor('shopify');
        void endpointRefs;
        return HttpResponse.json(rest);
      }),
    );
    renderApp('/apis/shopify?section=triggers');
    const card = await screen.findByRole('region', { name: 'Webhook delivery' });
    expect(
      within(card).getByText('post-admin-api-latest-webhooks-json-2026-10'),
    ).toBeInTheDocument();
    expect(within(card).queryByText('(not in this build)')).not.toBeInTheDocument();
    expect(within(card).queryByRole('link', { name: /orders\.json/ })).not.toBeInTheDocument();
  });

  it('a polled event says which endpoint it is polled through, resolved when the API can', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/triggers`, () =>
        HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          present: true,
          note: null,
          total: 1,
          webhooks: [],
          endpointRefs: {
            'get-orders-poll': {
              docId: 'endpoint:get-orders',
              method: 'GET',
              path: '/admin/api/latest/orders.json',
            },
          },
          items: [
            {
              key: 'orders/poll',
              docId: 'trigger:orders-poll',
              title: 'orders/poll',
              description: null,
              resource: null,
              delivery: 'polling',
              syncEndpointId: 'get-orders-poll',
            },
          ],
        }),
      ),
    );
    renderApp('/apis/shopify?section=triggers');
    const row = (await screen.findByRole('link', { name: 'orders/poll' })).closest(
      'li',
    ) as HTMLElement;
    expect(within(row).getByText(/Polled via/)).toBeInTheDocument();
    expect(
      within(row).getByRole('link', { name: '/admin/api/latest/orders.json' }),
    ).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('endpoint:get-orders')}`,
    );
  });
});

describe('MCP section', () => {
  it('appears only when the vendor runs an MCP server, with its tools', async () => {
    renderApp('/apis/stripe');
    const tab = await screen.findByRole('radio', { name: 'MCP (1)' });
    await userEvent.click(tab);
    const card = await screen.findByRole('region', { name: 'MCP' });
    expect(within(card).getByText('Stripe MCP')).toBeInTheDocument();
    expect(within(card).getByText('list_customers')).toBeInTheDocument();
    expect(within(card).getByText('create_invoice')).toBeInTheDocument();
    expect(within(card).getAllByText('Input schema')).toHaveLength(2);
    expect(within(card).getAllByText('Output schema')).toHaveLength(1);
  });

  it('renders nothing for a docs-only package: no tab, no empty state', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('radio', { name: 'Triggers (3)' });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole('radio', { name: /MCP/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/MCP/)).not.toBeInTheDocument();
  });

  it('ignores ?section=mcp when the package has no MCP server', async () => {
    renderApp('/apis/shopify?section=mcp');
    expect(await screen.findByRole('heading', { name: 'Browse' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'MCP' })).not.toBeInTheDocument();
  });
});
