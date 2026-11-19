import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { order40Snapshot } from '@/mocks/modelData';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

/** A real 40-field Order model (Shopify + WooCommerce + Mirakl), copied from a live snapshot. */
const url = `/models/${order40Snapshot.id}`;
const canonicalNodes = () => document.querySelectorAll('.react-flow__node-canonical').length;

describe('a big model (40 fields) opens as a readable table', () => {
  it('shows one row per field and one column per API, with display names', async () => {
    renderApp(url);
    const table = await screen.findByRole('table', { name: /How each API fills each field/ });
    expect(within(table).getAllByRole('row')).toHaveLength(41); // header + 40
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers).toEqual(['Field', 'Shopify', 'WooCommerce', 'Mirakl']); // the server sent "Woocommerce"
    expect(screen.getByRole('radio', { name: 'Table' })).toBeChecked();
    expect(screen.getByText('40 of 40 fields')).toBeInTheDocument();
    expect(screen.getByText('40 fields')).toBeInTheDocument(); // header chip
  });

  it('shows how each API fills a field: direct / derived / not supported, paths, transform, citations', async () => {
    renderApp(url);
    await screen.findByRole('table');
    const idRow = screen.getByRole('rowheader', { name: /^id/ }).closest('tr') as HTMLElement;
    const cells = within(idRow).getAllByRole('cell');
    expect(within(cells[0] as HTMLElement).getByText('derived')).toBeInTheDocument(); // Shopify
    expect(within(cells[2] as HTMLElement).getByText('direct')).toBeInTheDocument(); // Mirakl
    expect(within(cells[0] as HTMLElement).getByText(/1 citation/)).toBeInTheDocument();
    // a field a vendor lacks says so and shows no path
    const statusRow = screen
      .getByRole('rowheader', { name: /^status/ })
      .closest('tr') as HTMLElement;
    const statusCells = within(statusRow).getAllByRole('cell');
    expect(within(statusCells[0] as HTMLElement).getByText('not supported')).toBeInTheDocument();
    expect(within(statusCells[0] as HTMLElement).queryByRole('link')).not.toBeInTheDocument();
  });

  it('links each citation to the document it quotes', async () => {
    renderApp(url);
    await screen.findByRole('table');
    const idRow = screen.getByRole('rowheader', { name: /^id/ }).closest('tr') as HTMLElement;
    const shopifyCell = within(idRow).getAllByRole('cell')[0] as HTMLElement;
    await userEvent.click(within(shopifyCell).getByText(/1 citation/));
    const link = within(shopifyCell).getByRole('link');
    expect(link.getAttribute('href')).toBe(
      `/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/admin/api/{version}/orders/{order_id}/fulfillment_orders.json')}`,
    );
    await userEvent.click(link);
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      'fulfillment_orders.json',
    );
    expect(screen.getByRole('link', { name: 'Open the vendor page' })).toHaveAttribute(
      'href',
      expect.stringContaining('docs.example.com/shopify'),
    );
  });

  it('filters by text and by gaps', async () => {
    renderApp(url);
    await screen.findByRole('table');
    await userEvent.type(
      screen.getByRole('searchbox', { name: 'Filter fields' }),
      'display_number',
    );
    expect(screen.getByText('1 of 40 fields')).toBeInTheDocument();
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Filter fields' }));
    const gaps = screen.getByRole('button', { name: 'Only fields with gaps' });
    await userEvent.click(gaps);
    expect(gaps).toHaveAttribute('aria-pressed', 'true');
    const shown = Number(
      /(\d+) of 40 fields/.exec(screen.getByText(/ of 40 fields/).textContent ?? '')?.[1],
    );
    expect(shown).toBeGreaterThan(0);
    expect(shown).toBeLessThan(40);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Filter fields' }), 'zzzzzz');
    expect(screen.getByText('No field matches this filter.')).toBeInTheDocument();
  });

  it('keeps the coverage card readable: display names and counts together', async () => {
    renderApp(url);
    await screen.findByRole('table');
    const cov = screen.getByRole('heading', { name: 'Coverage' }).closest('div') as HTMLElement;
    expect(within(cov).getByText('WooCommerce')).toBeInTheDocument();
    expect(within(cov).getByText('26 of 40')).toBeInTheDocument();
    expect(within(cov).getByLabelText('WooCommerce: 26 of 40 fields')).toBeInTheDocument();
    expect(within(cov).queryByText('Woocommerce')).not.toBeInTheDocument();
  });

  it('has no mapping detail card in the table view (the table is the detail)', async () => {
    renderApp(url);
    await screen.findByRole('table');
    expect(screen.queryByRole('listbox', { name: 'Mappings' })).not.toBeInTheDocument();
  });
});

describe('a big model in the graph view: focus on one field, or the whole model', () => {
  async function openGraph() {
    renderApp(url);
    await screen.findByRole('table');
    await userEvent.click(screen.getByRole('radio', { name: 'Graph' }));
    await screen.findByRole('listbox', { name: 'Mappings' });
  }

  it('starts focused on the selected field, with only its API fields', async () => {
    await openGraph();
    expect(screen.getByRole('radio', { name: 'Selected field' })).toBeChecked();
    await waitFor(() => expect(canonicalNodes()).toBe(1));
    expect(
      screen.getByText('Pick a mapping in the list on the left to see it here.'),
    ).toBeInTheDocument();
  });

  it('shows the whole model on request, with pan and zoom instructions', async () => {
    await openGraph();
    await userEvent.click(screen.getByRole('radio', { name: 'Whole model' }));
    await waitFor(() => expect(canonicalNodes()).toBe(40));
    expect(screen.getByText(/Scroll to pan, Ctrl or ⌘ \+ scroll to zoom/)).toBeInTheDocument();
  });

  it('follows the mapping list: picking another field focuses the graph on it', async () => {
    await openGraph();
    await userEvent.click(screen.getByRole('option', { name: /display_number.*WooCommerce/ }));
    expect(
      screen.getByRole('heading', { name: 'display_number ← WooCommerce' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(canonicalNodes()).toBe(1));
    expect(document.querySelector('.react-flow__node-canonical')?.textContent).toContain(
      'display_number',
    );
  });

  it('says so when a focused field has no API behind it', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, () => {
        const m = structuredClone(order40Snapshot);
        for (const f of m.fields)
          f.support = { shopify: 'unsupported', woocommerce: 'unsupported', mirakl: 'unsupported' };
        return HttpResponse.json(m);
      }),
    );
    renderApp(url);
    await screen.findByRole('table');
    await userEvent.click(screen.getByRole('radio', { name: 'Graph' }));
    // defaultSelection finds no mapping: nothing is focused, so the empty message shows
    expect(await screen.findByText('No API fills this field.')).toBeInTheDocument();
  });
});

describe('a small model keeps the mockup: graph first', () => {
  it('opens as a graph with the whole model, and the table is one click away', async () => {
    renderApp('/models/snap_8f3a21');
    expect(await screen.findByRole('radio', { name: 'Graph' })).toBeChecked();
    expect(screen.queryByRole('radio', { name: 'Selected field' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Table' }));
    expect(
      await screen.findByRole('table', { name: /How each API fills each field/ }),
    ).toBeInTheDocument();
  });
});

describe('document page', () => {
  it("groups an endpoint's fields by where they go, and keeps long text and raw JSON collapsed", async () => {
    renderApp(
      '/apis/shopify/documents/' + encodeURIComponent('endpoint:POST~/api/orders/{order_id}'),
    );
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(screen.getByText('POST')).toBeInTheDocument();
    const path = within(screen.getByRole('region', { name: 'Path parameters' }));
    expect(path.getByText('order_id')).toBeInTheDocument();
    expect(path.getByText('required')).toBeInTheDocument();
    const body = within(screen.getByRole('region', { name: 'Request body' }));
    expect(body.getByText('order.total')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'Response fields' })).getByText('orders[].id'),
    ).toBeInTheDocument();
    expect(screen.getByText('v3')).toBeInTheDocument(); // tags
    expect(screen.getByText('Full text').closest('details')).not.toHaveAttribute('open');
    expect(
      screen.getByText('Source JSON, as in the package').closest('details'),
    ).not.toHaveAttribute('open');
  });

  it('a guide shows its text, no parameter tables and no vendor link when the package has none', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/documents/*`, async () => {
        const { sampleJob } = await import('@/mocks/jobData');
        void sampleJob;
        return HttpResponse.json({
          api: 'shopify',
          build: 'b-1',
          docsAsOf: '2026-11-14',
          id: 'guide:pagination',
          kind: 'guide',
          title: 'Pagination',
          resource: null,
          method: null,
          path: null,
          deprecated: false,
          complete: true,
          sourceUrl: null,
          anchor: null,
          text: '# Pagination\n\nUse page_info.',
          fields: [],
          scopes: [],
        });
      }),
    );
    renderApp('/apis/shopify/documents/guide%3Apagination');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Pagination' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Use page_info\./)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('No vendor link in the package')).toBeInTheDocument();
    expect(screen.queryByText('Source JSON, as in the package')).not.toBeInTheDocument();
  });

  it('shows a stored document as plain text, with its fields and a link to the vendor page', async () => {
    renderApp('/apis/shopify/documents/' + encodeURIComponent('model:order'));
    expect(screen.getByRole('status')).toHaveTextContent('Loading the document');
    expect(await screen.findByRole('heading', { level: 1, name: 'Order' })).toBeInTheDocument();
    expect(screen.getByText(/Total amount billed for the order/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Fields' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the vendor page' })).toHaveAttribute(
      'rel',
      'noreferrer',
    );
  });

  it('shows not found and errors', async () => {
    const { unmount } = renderApp('/apis/nope/documents/model%3Aorder');
    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found');
    unmount();
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/documents/*`, () =>
        HttpResponse.json({ error: 'internal', message: 'index offline' }, { status: 500 }),
      ),
    );
    renderApp('/apis/shopify/documents/model%3Aorder');
    expect(await screen.findByText('Could not load this document')).toBeInTheDocument();
  });
});
