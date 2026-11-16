import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { REVIEW_SHOPIFY_NEW } from '@/mocks/releaseStore';
import { DocsUpdatedBadge, docsUpdatedText } from '@/components/DocsUpdatedBadge';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import type { PublicChange } from '@/api/types';
import { MemoryRouter } from 'react-router-dom';
import { ChangeBrief, vendorHref } from './ChangeBrief';
import { filterCount, filterQuery, groupByDocument } from './ChangesTab';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
});

const base = (over: Partial<PublicChange> = {}): PublicChange => ({
  id: 'ch-1',
  kind: 'param',
  op: 'removed',
  subject: {
    docId: 'endpoint:GET~/orders.json',
    method: 'GET',
    path: '/orders.json',
    fieldPath: 'limit',
  },
  before: { type: 'integer', required: false },
  after: null,
  breaking: true,
  breakingReason: 'query parameter removed',
  class: 'confirmed',
  quote: 'How many orders to return.',
  vendorUrl: 'https://shopify.dev/docs/orders',
  anchor: 'limit',
  ...over,
});

describe('the docs-updated badge', () => {
  it('says what changed in text, with the breaking count, and leads to the Changes tab', () => {
    const d = { build: 'b-1', at: '2026-11-14', confirmed: 3, likely: 1, breaking: 2 };
    expect(docsUpdatedText(d)).toBe('Docs updated 14 Nov 2026: 4 changes, 2 breaking');
    expect(docsUpdatedText({ ...d, confirmed: 1, likely: 0, breaking: 0 })).toBe(
      'Docs updated 14 Nov 2026: 1 change',
    );
    render(
      <MemoryRouter>
        <DocsUpdatedBadge api="shopify" docsUpdated={d} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/apis/shopify?section=changes&build=b-1',
    );
  });
  it('renders nothing for null, absent, or nothing but wording', () => {
    const { container, rerender } = render(
      <MemoryRouter>
        <DocsUpdatedBadge api="shopify" docsUpdated={null} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(
      <MemoryRouter>
        <DocsUpdatedBadge api="shopify" />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(
      <MemoryRouter>
        <DocsUpdatedBadge
          api="shopify"
          docsUpdated={{
            build: 'b',
            at: '2026-11-14',
            confirmed: 0,
            likely: 0,
            breaking: 0,
            wordingOnly: 4,
          }}
        />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
  it('shows on the home card of an API whose latest build has visible changes, and only there', async () => {
    renderApp('/');
    const card = (await screen.findByRole('link', { name: /Shopify/ })).closest(
      'article',
    ) as HTMLElement;
    expect(
      within(card).getByRole('link', { name: /Docs updated 14 Nov 2026: 3 changes, 2 breaking/ }),
    ).toBeInTheDocument();
    // only the API whose latest build has notes says it: the other cards do not
    expect(screen.getAllByText(/Docs updated/)).toHaveLength(1);
  });
});

describe('helpers', () => {
  it('chip counts come from the totals of the whole build without wording; wording from the timeline', () => {
    const t = {
      confirmed: 2,
      likely: 1,
      breaking: 2,
      wordingOnly: 0,
      byKind: { param: 1, webhook_event: 1, response_field: 1 },
    };
    expect(filterCount('all', t, 1)).toBe(3);
    expect(filterCount('breaking', t, 1)).toBe(2);
    expect(filterCount('wording', t, 1)).toBe(1);
    expect(filterCount('endpoints', t, 1)).toBe(1);
    expect(filterCount('fields', t, 1)).toBe(2);
    expect(filterCount('auth', t, 1)).toBe(0);
    expect(filterCount('fields', { ...t, byKind: undefined }, 1)).toBeNull();
  });
  it('a kind group is asked for as a comma list; breaking and wording have their own flags', () => {
    expect(filterQuery('breaking')).toEqual({ breaking: true, wordingOnly: false });
    expect(filterQuery('wording')).toEqual({ wordingOnly: true });
    expect(filterQuery('all')).toEqual({ wordingOnly: false });
    expect(filterQuery('fields')).toEqual({
      kind: 'param,request_field,response_field,model,property',
      wordingOnly: false,
    });
    expect(filterQuery('auth').kind).toBe('auth_scheme,scope');
    expect(filterQuery('endpoints').kind).toBe('endpoint,webhook_event');
  });
  it('groups by document in the order they first appear', () => {
    const g = groupByDocument([
      base({ id: 'a' }),
      base({ id: 'b', subject: { docId: 'model:order', model: 'Order' } }),
      base({ id: 'c' }),
    ]);
    expect(g.map((x) => [x.title, x.items.length])).toEqual([
      ['GET /orders.json', 2],
      ['Order model', 1],
    ]);
  });
  it('a vendor link is http(s) only and carries the anchor without a doubled #', () => {
    expect(vendorHref(base())).toBe('https://shopify.dev/docs/orders#limit');
    expect(vendorHref(base({ anchor: '#limit' }))).toBe('https://shopify.dev/docs/orders#limit');
    expect(vendorHref(base({ anchor: null }))).toBe('https://shopify.dev/docs/orders');
    expect(vendorHref(base({ vendorUrl: 'javascript:alert(1)' }))).toBeNull();
    expect(vendorHref(base({ vendorUrl: null }))).toBeNull();
  });
});

describe('one change', () => {
  const view = (c: PublicChange) =>
    render(
      <MemoryRouter>
        <ul>
          <ChangeBrief api="shopify" item={c} />
        </ul>
      </MemoryRouter>,
    );
  it('shows op, BREAKING as text, before → after, the quote as plain text and both links', () => {
    view(base({ op: 'type', after: { type: 'string' }, kind: 'param' }));
    const li = screen.getByRole('listitem');
    expect(li).toHaveTextContent('type changed');
    expect(li).toHaveTextContent('Breaking');
    expect(li).toHaveTextContent('query parameter removed');
    expect(li).toHaveTextContent('How many orders to return.');
    expect(within(li).getByRole('link', { name: 'Vendor page' })).toHaveAttribute(
      'target',
      '_blank',
    );
    expect(within(li).getByRole('link', { name: 'Open in Plume' })).toHaveAttribute(
      'href',
      '/apis/shopify/documents/endpoint%3AGET~%2Forders.json',
    );
  });
  it('a quote with markup stays text; a likely change says whose word it is; a removed document has no link in Plume', () => {
    view(
      base({
        quote: '<img src=x onerror=alert(1)> **bold**',
        class: 'likely',
        perVendorChangelog: true,
        removedDocument: true,
        op: 'removed',
        vendorUrl: null,
      }),
    );
    const li = screen.getByRole('listitem');
    expect(li).toHaveTextContent('<img src=x onerror=alert(1)> **bold**');
    expect(li.querySelector('img, b, strong')).toBeNull();
    expect(li).toHaveTextContent("Per the vendor's changelog");
    expect(within(li).queryByRole('link')).not.toBeInTheDocument();
    expect(li).toHaveTextContent('No vendor page');
  });
  it('a change that is not breaking carries no BREAKING mark', () => {
    view(
      base({
        breaking: false,
        breakingReason: null,
        op: 'added',
        before: null,
        after: { type: 'string' },
      }),
    );
    expect(screen.getByRole('listitem')).not.toHaveTextContent('Breaking');
  });
});

describe('the Changes tab', () => {
  const tab = '/apis/shopify?section=changes';
  const open = async (path = tab) => {
    renderApp(path);
    return screen.findByRole('region', { name: /^Changes of / });
  };

  it('is a section only for an API with notes; its timeline lists builds newest first with counts', async () => {
    const panel = await open();
    const timeline = screen.getByRole('list', { name: 'Builds' });
    const rows = within(timeline).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('14 Nov 2026');
    expect(rows[0]).toHaveTextContent('latest');
    expect(rows[0]).toHaveTextContent('Breaking');
    expect(rows[0]).toHaveTextContent('3 changes · 1 wording only');
    expect(rows[1]).toHaveTextContent('20 Oct 2026');
    expect(rows[1]).toHaveTextContent('1 change');
    expect(rows[1]).not.toHaveTextContent('Breaking');
    expect(panel).toBeInTheDocument();
  });

  it('lists the visible changes grouped by document, breaking first, wording kept apart', async () => {
    const panel = await open();
    await within(panel).findByRole('region', { name: 'GET /admin/api/latest/orders.json' });
    expect(
      within(panel).queryByText(/A note about the order, set by the merchant/),
    ).not.toBeInTheDocument();
    expect(panel).toHaveTextContent('Wording only: 1 description changed.');
    // a likely one says whose word it is
    expect(panel).toHaveTextContent("Per the vendor's changelog");
    // the order: breaking before the addition
    const items = within(panel)
      .getAllByRole('listitem')
      .map((li) => li.textContent ?? '');
    expect(items.findIndex((t) => t.includes('fulfillment_status'))).toBeLessThan(
      items.findIndex((t) => t.includes('note_attributes')),
    );
    await userEvent.click(within(panel).getByRole('button', { name: 'Show them' }));
    expect(
      await screen.findByText(/A note about the order, set by the merchant/),
    ).toBeInTheDocument();
  });

  it('chips carry the counts of the whole build; Breaking and a kind group filter; the filter is in the URL', async () => {
    const panel = await open();
    await within(panel).findByRole('region', { name: 'GET /admin/api/latest/orders.json' });
    const chip = (name: RegExp) =>
      within(panel).getByRole('radio', { name }).closest('label') as HTMLElement;
    await waitFor(() => expect(chip(/^All/)).toHaveTextContent('3'));
    expect(chip(/^Breaking/)).toHaveTextContent('2');
    expect(chip(/^Endpoints/)).toHaveTextContent('1');
    expect(chip(/^Fields/)).toHaveTextContent('2');
    expect(chip(/^Wording only/)).toHaveTextContent('1');
    await userEvent.click(chip(/^Breaking/));
    await waitFor(() =>
      expect(within(panel).queryByText(/note_attributes/)).not.toBeInTheDocument(),
    );
    expect(within(panel).getByText(/fulfillment_status/)).toBeInTheDocument();
    // the counts did not move with the filter
    expect(chip(/^All/)).toHaveTextContent('3');
    await userEvent.click(chip(/^Endpoints/));
    await waitFor(() =>
      expect(within(panel).queryByText(/fulfillment_status/)).not.toBeInTheDocument(),
    );
    expect(within(panel).getByText(/tax_lines/)).toBeInTheDocument();
    expect(within(panel).getByRole('radio', { name: /^Endpoints/ })).toBeChecked();
  });

  it('a kind group is one server request with a comma list, and "Show more" pages the same selection', async () => {
    const urls: string[] = [];
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes`, ({ request }) => {
        urls.push(request.url);
        const q = new URL(request.url).searchParams;
        const cursor = Number(q.get('cursor') ?? 0);
        const item = (n: number) => ({
          id: `ch-f${n}`,
          kind: 'param',
          op: 'added',
          subject: { docId: 'endpoint:GET~/x', method: 'GET', path: '/x', fieldPath: `p${n}` },
          breaking: false,
          class: 'confirmed',
        });
        return HttpResponse.json({
          totals: {
            confirmed: 150,
            likely: 0,
            breaking: 0,
            wordingOnly: 0,
            byKind: { param: 150 },
          },
          items: Array.from({ length: cursor === 0 ? 100 : 50 }, (_, i) => item(cursor + i)),
          nextCursor: cursor === 0 ? 100 : null,
        });
      }),
    );
    const panel = await open(`${tab}&filter=fields`);
    await waitFor(() => expect(within(panel).getAllByRole('listitem')).toHaveLength(100));
    const group = urls.filter((u) => new URL(u).searchParams.has('kind'));
    expect(group.length).toBeGreaterThan(0);
    expect(new URL(group[0] ?? '').searchParams.get('kind')).toBe(
      'param,request_field,response_field,model,property',
    );
    expect(new URL(group[0] ?? '').searchParams.get('wordingOnly')).toBe('false');
    await userEvent.click(within(panel).getByRole('button', { name: 'Show more' }));
    await waitFor(() => expect(within(panel).getAllByRole('listitem')).toHaveLength(150));
    expect(new URL(urls[urls.length - 1] ?? '').searchParams.get('cursor')).toBe('100');
    expect(new URL(urls[urls.length - 1] ?? '').searchParams.get('kind')).toContain('param');
    expect(within(panel).queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
  });

  it('a search narrows the list; "No changes match" says so', async () => {
    const panel = await open();
    await within(panel).findByRole('region', { name: 'GET /admin/api/latest/orders.json' });
    await userEvent.type(within(panel).getByLabelText(/Search the changes/), 'zzz-nothing');
    expect(
      await within(panel).findByText('No changes match this filter.', {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it('opening an older build lists its own changes', async () => {
    const panel = await open();
    await within(panel).findByRole('region', { name: 'GET /admin/api/latest/orders.json' });
    await userEvent.click(screen.getByRole('button', { name: '20 Oct 2026' }));
    const older = await screen.findByRole('region', { name: 'Changes of 20 Oct 2026' });
    expect((await within(older).findAllByText(/gift_cards/)).length).toBeGreaterThan(0);
    expect(within(older).queryByText(/fulfillment_status/)).not.toBeInTheDocument();
  });

  it('links the Atom feed and says when a deep link is no longer listed', async () => {
    const panel = await open(`${tab}&item=ch-gone`);
    const atom = screen.getByRole('link', { name: 'Subscribe (Atom)' });
    expect(atom).toHaveAttribute('href', `${TEST_API_BASE}/v1/apis/shopify/changes.atom`);
    expect(await within(panel).findByText(/That change is no longer listed/)).toBeInTheDocument();
  });

  it('highlights the change a deep link names', async () => {
    const panel = await open(`${tab}&item=ch-orders-fulfillment-status`);
    const hit = await waitFor(() => {
      const el = panel.querySelector('.change-hit');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    expect(hit).toHaveTextContent('fulfillment_status');
  });

  it('an empty build reads "No API changes found"', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes`, () =>
        HttpResponse.json({
          totals: { confirmed: 0, likely: 0, breaking: 0, wordingOnly: 0, byKind: {} },
          items: [],
          nextCursor: null,
        }),
      ),
    );
    const panel = await open();
    expect(await within(panel).findByText('No API changes found.')).toBeInTheDocument();
  });

  it('a page that cannot be loaded says so', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes`, () =>
        HttpResponse.json({ error: 'x', message: 'the changes are down' }, { status: 500 }),
      ),
    );
    const panel = await open();
    expect(await within(panel).findByRole('alert')).toHaveTextContent('the changes are down');
  });

  it('asks the server for a build the timeline named, and shows no tab for an API without notes or a server without the route', async () => {
    const urls: string[] = [];
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes`, ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({
          totals: { confirmed: 0, likely: 0, breaking: 0, wordingOnly: 0 },
          items: [],
          nextCursor: null,
        });
      }),
    );
    await open(`${tab}&build=${REVIEW_SHOPIFY_NEW}`);
    await waitFor(() =>
      expect(urls.some((u) => u.includes(`build=${REVIEW_SHOPIFY_NEW}`))).toBe(true),
    );
  });
});

describe('feature detection', () => {
  it('no Changes section for an API without notes', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes/timeline`, () =>
        HttpResponse.json({ api: 'shopify', items: [] }),
      ),
    );
    renderApp('/apis/shopify?section=changes');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByRole('radio', { name: 'Changes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /^Changes of / })).not.toBeInTheDocument();
  });
  it('no Changes section and no error for a server without the routes', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/changes/timeline`, () =>
        HttpResponse.json({ error: 'not_found', message: 'no' }, { status: 404 }),
      ),
    );
    renderApp('/apis/shopify?section=changes');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByRole('radio', { name: 'Changes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /^Changes of / })).not.toBeInTheDocument();
  });
  it('the section is offered on an API with notes and the badge in its header leads to it', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(await screen.findByRole('radio', { name: 'Changes' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Docs updated 14 Nov 2026/ })).toHaveAttribute(
      'href',
      expect.stringContaining('section=changes'),
    );
  });
});
