import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { collapseSources, SourcesLine, sourceLabel } from '@/components/SourcesLine';
import { createHandlers } from '@/mocks/handlers';
import { shopifyDetail } from '@/mocks/data';
import { REVIEW_SHOPIFY_NEW, REVIEW_SHOPIFY_OLD } from '@/mocks/releaseStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

describe('public: where the docs came from', () => {
  it('shows ONE compact line: linked sources of one each, and when it was extracted (no tail)', async () => {
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    const line = screen.getByTestId('sources-line');
    const links = within(line).getAllByRole('link');
    expect(links.map((l) => l.textContent)).toEqual(['Docs', 'OpenAPI spec', 'Changelog']);
    expect(links[1]).toHaveAttribute('href', 'https://shopify.dev/openapi/admin-rest.json');
    for (const l of links) {
      expect(l).toHaveAttribute('target', '_blank');
      expect(l).toHaveAttribute('rel', expect.stringContaining('noopener'));
    }
    expect(line).toHaveTextContent(
      'Sources: Docs · OpenAPI spec · Changelog · Extracted 14 Nov 2026',
    );
    // the redundant tail is gone
    expect(line).not.toHaveTextContent(/from docs/i);
    expect(screen.getByText('latest · docs as of 14 Nov 2026')).toBeInTheDocument();
  });

  it('a package with one source: Docs links directly, no disclosure', async () => {
    renderApp('/apis/stripe');
    await screen.findByRole('heading', { level: 1, name: 'Stripe API' });
    const line = screen.getByTestId('sources-line');
    expect(within(line).getAllByRole('link')).toHaveLength(1);
    expect(line).toHaveTextContent('Sources: Docs · Extracted 14 Nov 2026');
    expect(screen.queryByTestId('sources-detail')).not.toBeInTheDocument();
  });

  it('many sources: counts per kind in one line, a disclosure lists each one with readable names', async () => {
    renderApp('/apis/amazon-sp-vendor');
    await screen.findByRole('heading', { level: 1, name: /Amazon SP-API/ });
    const line = screen.getByTestId('sources-line');
    expect(line).toHaveTextContent(
      'Sources: Docs · 13 OpenAPI specs · Changelog · Extracted 16 Nov 2026',
    );
    // the two changelog hosts are the same page: one entry
    expect(line).not.toHaveTextContent('2 changelogs');
    const detail = screen.getByTestId('sources-detail');
    expect(detail).toHaveTextContent('All sources (15)');
    const items = within(detail).getAllByRole('listitem');
    expect(items).toHaveLength(15);
    // a spec is its file name, its host is secondary, with kind and fetch date
    const orders = within(detail).getByRole('link', { name: 'vendorOrders.json' });
    expect(orders).toHaveAttribute(
      'href',
      expect.stringContaining('raw.githubusercontent.com/amzn/selling-partner-api-models'),
    );
    const row = orders.closest('li') as HTMLElement;
    expect(row).toHaveTextContent('raw.githubusercontent.com');
    expect(row).toHaveTextContent('OpenAPI spec');
    expect(row).toHaveTextContent('fetched 16 Nov 2026');
    expect(
      within(detail).getByRole('link', { name: 'vendorDirectFulfillmentShipping_2021-12-28.json' }),
    ).toBeInTheDocument();
    // the alias host is kept in the detail, the .com one is the link
    const changelog = within(detail).getByRole('link', { name: 'Changelog' });
    expect(changelog).toHaveAttribute('href', 'https://developer-docs.amazon.com/sp-api/changelog');
    expect(changelog.closest('li')).toHaveTextContent('also linked as developer-docs.amazon');
  });

  it('renders nothing for an older build without the fields (null) and nothing for none', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id`, () =>
        HttpResponse.json({ ...shopifyDetail, sources: null, extractedAt: null }),
      ),
    );
    renderApp('/apis/shopify');
    await screen.findByRole('heading', { level: 1, name: 'Shopify Admin REST API' });
    expect(screen.queryByTestId('sources')).not.toBeInTheDocument();
    expect(screen.queryByText(/Extracted/)).not.toBeInTheDocument();
  });

  it('shows only what exists: no sources but a date, or sources but no date', () => {
    const { rerender } = render(<SourcesLine sources={[]} extractedAt="2026-11-14T08:30:00Z" />);
    expect(screen.getByTestId('sources-line')).toHaveTextContent('Extracted 14 Nov 2026');
    expect(screen.getByTestId('sources-line')).not.toHaveTextContent('Sources');
    rerender(
      <SourcesLine sources={[{ url: 'https://a.dev/x', kind: 'docs' }]} extractedAt={null} />,
    );
    expect(screen.getByTestId('sources-line')).toHaveTextContent('Sources: Docs');
    expect(screen.queryByText(/Extracted/)).not.toBeInTheDocument();
  });

  it('links only http(s) and calls an unknown kind "other"', () => {
    render(
      <SourcesLine
        sources={[
          { url: 'javascript:alert(1)', kind: 'docs' },
          { url: 'https://a.dev/docs', kind: 'docs' },
          { url: 'https://c.dev/x', kind: 'mystery' },
        ]}
        extractedAt={null}
      />,
    );
    expect(
      within(screen.getByTestId('sources-line'))
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual(['Docs', 'Other']);
    expect(document.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it('collapses a host alias (www., a missing .com) onto the .com host and keeps it as "also linked as"', () => {
    const g = collapseSources([
      { url: 'https://developer-docs.amazon/sp-api/changelog', kind: 'changelog' },
      { url: 'https://developer-docs.amazon.com/sp-api/changelog/', kind: 'changelog' },
      { url: 'https://www.example.org/docs', kind: 'docs' },
      { url: 'https://example.org/docs', kind: 'docs' },
      { url: 'https://other.dev/docs', kind: 'docs' },
    ]);
    expect(g).toHaveLength(3);
    expect(g[0]?.primary.url).toBe('https://developer-docs.amazon.com/sp-api/changelog/');
    expect(g[0]?.aliases.map((a) => a.url)).toEqual([
      'https://developer-docs.amazon/sp-api/changelog',
    ]);
    // a different path or kind is not an alias
    expect(
      collapseSources([
        { url: 'https://a.com/x', kind: 'docs' },
        { url: 'https://a.com/y', kind: 'docs' },
        { url: 'https://a.com/x', kind: 'spec' },
      ]),
    ).toHaveLength(3);
  });

  it('labels a spec by its file name, anything else by what it is', () => {
    expect(sourceLabel({ url: 'https://h.com/m/vendor%20Orders.json', kind: 'spec' })).toBe(
      'vendor Orders.json',
    );
    expect(sourceLabel({ url: 'https://h.com/', kind: 'spec' })).toBe('OpenAPI spec');
    expect(sourceLabel({ url: 'https://h.com/a/b', kind: 'changelog' })).toBe('Changelog');
  });
});

describe('maintainer: sources, run and conflicts in the review', () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(...createHandlers(TEST_API_BASE));
    authStore.signIn('pl_ok', 'maintainer');
  });
  afterEach(() => authStore.signOut());

  it('lists the sources with the run, the conflicts as text, and never calls "not compared" no conflicts', async () => {
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`);
    await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
    const panel = screen.getByRole('region', { name: 'Sources and conflicts' });
    expect(panel).toHaveTextContent('run-20261114-0830');
    const list = within(panel).getByRole('list', { name: 'Sources of this build' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(list).toHaveTextContent('OpenAPI spec');
    expect(list).toHaveTextContent('discovered from https://shopify.dev/docs/api/admin-rest');
    expect(panel).toHaveTextContent('https://shopify.dev/changelog');
    const check = within(panel).getByTestId('conflict-check');
    expect(check).toHaveTextContent('Stream compared 38 units');
    expect(check).toHaveTextContent('6 units not compared');
    expect(check).toHaveTextContent('not the same as “no conflicts”');
    expect(check).not.toHaveTextContent('found no conflicts');
    const conflicts = within(panel).getByRole('list', { name: 'Source conflicts' });
    expect(conflicts).toHaveTextContent('param limit: maximum');
    // hostile text from a package stays text
    expect(conflicts).toHaveTextContent('<script>alert(1)</script> 100');
    expect(conflicts.querySelector('script')).toBeNull();
    expect(conflicts).toHaveTextContent('Stream chose 250: the docs page is newer than the spec');
    // the run id is also in the package card
    expect(screen.getByRole('region', { name: 'Package and quality' })).toHaveTextContent(
      'run-20261114-0830',
    );
  });

  it('a change says where it comes from only when that was recorded', async () => {
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`);
    await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
    const users = screen.getByRole('region', { name: 'Changes users see' });
    expect(users).toHaveTextContent('Source: OpenAPI spec · shopify.dev');
    expect(users).toHaveTextContent('Source attribution: not recorded.');
    const report = screen.getAllByRole('region', { name: 'Alphabetical cut-off' })[0];
    expect(report).toHaveTextContent('Source attribution: not recorded.');
  });

  it('an older build (no fields) shows no sources card and never claims there are no conflicts', async () => {
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_OLD}/notes`);
    await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
    expect(screen.queryByRole('region', { name: 'Sources and conflicts' })).not.toBeInTheDocument();
    expect(screen.queryByText(/no conflicts/i)).not.toBeInTheDocument();
  });

  it('a check that compared nothing says no check was recorded, not "no conflicts"', async () => {
    const base = `${TEST_API_BASE}/v1/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/release-notes`;
    const real = await fetch(base, { headers: { Authorization: 'Bearer pl_ok' } }).then((r) =>
      r.json(),
    );
    server.use(
      http.get(base, () =>
        HttpResponse.json({
          ...real,
          conflicts: [],
          conflictCheck: { checked: 0, notCompared: 0 },
        }),
      ),
    );
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`);
    await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
    const check = screen.getByTestId('conflict-check');
    expect(check).toHaveTextContent('no conflict check was recorded');
    expect(check).not.toHaveTextContent('found no conflicts');
    expect(check).not.toHaveTextContent('compared 0');
  });

  it('all compared and none found says so; conflicts without the check still list', async () => {
    const base = `${TEST_API_BASE}/v1/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/release-notes`;
    const real = await fetch(base, { headers: { Authorization: 'Bearer pl_ok' } }).then((r) =>
      r.json(),
    );
    server.use(
      http.get(base, () =>
        HttpResponse.json({
          ...real,
          conflicts: [],
          conflictCheck: { checked: 12, notCompared: 0 },
        }),
      ),
    );
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`);
    await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
    const check = screen.getByTestId('conflict-check');
    expect(check).toHaveTextContent(
      'Stream compared 12 units across sources and found no conflicts.',
    );
    expect(check).not.toHaveTextContent('not compared');
    await userEvent.click(document.body);
  });
});
