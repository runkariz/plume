import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { inventorySnapshot } from '@/mocks/modelData';
import { renderApp } from '@/test/render';
import { ConversionChip, unmappedValues } from './Conversion';
import { endpointDocId, endpointTarget, Operations } from './Operations';

describe('endpoint ids', () => {
  it('reads "METHOD path" as the document id, and the cited document wins when it has an operation suffix', () => {
    expect(endpointDocId('post /a/{id}.json')).toBe('endpoint:POST~/a/{id}.json');
    expect(endpointDocId('nonsense')).toBeNull();
    expect(
      endpointTarget({
        endpoint: 'GET /f',
        fields: [],
        evidence: [{ quote: 'q', anchor: '', docId: 'endpoint:GET~/f@get-or15' }],
      }),
    ).toBe('endpoint:GET~/f@get-or15');
    expect(endpointTarget({ endpoint: 'GET /f', fields: [], evidence: [] })).toBe(
      'endpoint:GET~/f',
    );
  });
});

describe('Operations', () => {
  it('shows nothing when the model states no operations', () => {
    expect(
      render(<Operations snap={{ ...inventorySnapshot, operations: undefined }} />).container,
    ).toBeEmptyDOMElement();
    expect(
      render(<Operations snap={{ ...inventorySnapshot, operations: [] }} />).container,
    ).toBeEmptyDOMElement();
  });

  it('is a row per operation and a column per API, with endpoint link, fields and semantics', () => {
    render(
      <Operations
        snap={inventorySnapshot}
        endpointLink={(api, docId, label) => (
          <a href={`/apis/${api}/documents/${encodeURIComponent(docId)}`}>{label}</a>
        )}
      />,
    );
    const card = screen.getByRole('region', { name: 'Operations' });
    const headers = within(card)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers).toEqual(['Operation', 'Shopify', 'WooCommerce', 'Mirakl']);
    const set = within(card)
      .getByRole('rowheader', { name: /set absolute stock/ })
      .closest('tr') as HTMLElement;
    expect(within(set).getByText('set')).toBeInTheDocument();
    const link = within(set).getByRole('link', {
      name: 'POST /admin/api/{version}/inventory_levels/set.json',
    });
    // the cited document names the endpoint
    expect(link).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('endpoint:POST~/admin/api/{version}/inventory_levels/set.json')}`,
    );
    expect(within(set).getByText('absolute; omitted means 0')).toBeInTheDocument();
    expect(within(set).getByText('available')).toBeInTheDocument();
    // Mirakl has no way to do it
    expect(within(set).getByText('No equivalent')).toBeInTheDocument();
    // WooCommerce's endpoint is a link built from the line
    expect(
      within(set).getByRole('link', { name: 'PUT /wp-json/wc/v3/products/{id}' }),
    ).toHaveAttribute(
      'href',
      `/apis/woocommerce/documents/${encodeURIComponent('endpoint:PUT~/wp-json/wc/v3/products/{id}')}`,
    );
  });

  it('is plain text without a link builder', () => {
    render(<Operations snap={inventorySnapshot} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(
      screen.getByText('POST /admin/api/{version}/inventory_levels/set.json'),
    ).toBeInTheDocument();
  });

  it('is on the model page, links an endpoint to its page', async () => {
    const { router } = renderApp('/models/snap_8f3a21');
    const card = await screen.findByRole('region', { name: 'Operations' });
    await userEvent.click(
      within(card).getByRole('link', { name: 'GET /admin/api/{version}/inventory_levels.json' }),
    );
    expect(router.state.location.pathname).toBe(
      `/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/admin/api/{version}/inventory_levels.json')}`,
    );
  });
});

describe('unmapped enum values', () => {
  it('are listed as "not mapped" in the chip detail', async () => {
    render(
      <ConversionChip
        conversion={{ kind: 'enum', map: { a: 'x' }, unmapped: ['preorder', 'on_request'] }}
      />,
    );
    await userEvent.click(screen.getByText('enum map'));
    expect(screen.getByText('not mapped:').parentElement).toHaveTextContent(
      'not mapped: preorder, on_request',
    );
  });
  it('make a bare chip openable, and bad values are dropped', () => {
    const { container } = render(<ConversionChip conversion={{ kind: 'enum', unmapped: ['x'] }} />);
    expect(container.querySelector('details')).not.toBeNull();
    expect(unmappedValues({ kind: 'enum', unmapped: ['a', {} as never, 3 as never] })).toEqual([
      'a',
      '3',
    ]);
  });
});

describe('evidence without a quote', () => {
  const reason =
    "cited without quote: the field's own description is only a label (Stock management)";
  it('says why in the table', async () => {
    renderApp('/models/snap_8f3a21');
    await userEvent.click(await screen.findByRole('radio', { name: 'Table' }));
    const row = (await screen.findByRole('rowheader', { name: /^manage_stock/ })).closest(
      'tr',
    ) as HTMLElement;
    const woo = Array.from(row.querySelectorAll(':scope > td'))[1] as HTMLElement;
    await userEvent.click(within(woo).getByText(/1 citation/));
    expect(within(woo).getByText(reason)).toBeInTheDocument();
  });

  it('says why in the mapping detail', async () => {
    renderApp('/models/snap_8f3a21?field=manage_stock&api=woocommerce');
    const detail = await screen.findByRole('region', { name: 'Mapping detail' });
    expect(await within(detail).findByText(reason)).toBeInTheDocument();
    expect(within(detail).queryByText(/“”/)).not.toBeInTheDocument();
  });
});
