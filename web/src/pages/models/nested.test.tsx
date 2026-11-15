import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { nestedSnapshot } from '@/mocks/modelData';
import { NESTED } from '@/mocks/modelStore';
import { renderApp } from '@/test/render';
import type { ModelSnapshot } from '@/api/types';
import { countLeaves, findField, flatten, hasOwnSources, mappedFields, withPaths } from './fields';
import { buildGraph, canonNodeId, mappingRows } from './graph';

const search = (router: { state: { location: { search: string } } }) =>
  new URLSearchParams(router.state.location.search);

describe('nested fields: the helpers', () => {
  const snap = nestedSnapshot;

  it('flattens parents before their children, with depth and parent', () => {
    expect(flatten(snap.fields).map((x) => [x.path, x.depth, x.parent, x.container])).toEqual([
      ['id', 0, null, false],
      ['customer', 0, null, true],
      ['customer.name', 1, 'customer', false],
      ['customer.email', 1, 'customer', false],
      ['lines', 0, null, true],
      ['lines[].sku', 1, 'lines', false],
      ['lines[].price', 1, 'lines', true],
      ['lines[].price.amount', 2, 'lines[].price', false],
      ['lines[].price.currency', 2, 'lines[].price', false],
    ]);
  });

  it('counts leaves only, and maps leaves plus the containers that have sources of their own', () => {
    expect(countLeaves(snap)).toBe(6);
    // customer and lines[].price only group their children; lines is mapped as a whole too
    expect(mappedFields(snap).map((x) => x.path)).toEqual([
      'id',
      'customer.name',
      'customer.email',
      'lines',
      'lines[].sku',
      'lines[].price.amount',
      'lines[].price.currency',
    ]);
    expect(hasOwnSources(findField(snap, 'lines')?.field as never)).toBe(true);
    expect(hasOwnSources(findField(snap, 'customer')?.field as never)).toBe(false);
  });

  it('finds a field by its canonical path', () => {
    expect(findField(snap, 'lines[].price.amount')?.field.name).toBe('amount');
    expect(findField(snap, 'amount')).toBeUndefined(); // the name alone is not the path
  });

  it('gives canonical paths to fields the server did not (arrays use [], objects a dot)', () => {
    const bare = {
      ...snap,
      fields: [
        {
          name: 'lines',
          type: 'array',
          required: false,
          support: {},
          sources: {},
          fields: [
            {
              name: 'price',
              type: 'object',
              required: false,
              support: {},
              sources: {},
              fields: [
                { name: 'amount', type: 'string', required: false, support: {}, sources: {} },
              ],
            },
          ],
        },
      ],
    } as unknown as ModelSnapshot;
    expect(flatten(withPaths(bare).fields).map((x) => x.path)).toEqual([
      'lines',
      'lines[].price',
      'lines[].price.amount',
    ]);
    // a flat model is unchanged
    expect(
      withPaths({
        ...snap,
        fields: [{ ...(snap.fields[0] as ModelSnapshot['fields'][number]), path: undefined }],
      }).fields[0]?.path,
    ).toBe('id');
  });
});

describe('nested fields: the graph and the list', () => {
  const snap = nestedSnapshot;

  it('draws leaves (and a container mapped as a whole), by path; edges go per mapped field', () => {
    const g = buildGraph(snap);
    const canon = g.nodes.filter((n) => n.data.kind === 'canonical').map((n) => n.id);
    expect(canon).toEqual(
      [
        'id',
        'customer.name',
        'customer.email',
        'lines',
        'lines[].sku',
        'lines[].price.amount',
        'lines[].price.currency',
      ].map(canonNodeId),
    );
    expect(g.nodes.some((n) => n.id === canonNodeId('customer'))).toBe(false); // groups only
    expect(
      g.edges.some(
        (e) => e.data?.field === 'lines[].price.amount' && e.data.apiId === 'woocommerce',
      ),
    ).toBe(true);
    expect(g.edges.some((e) => e.data?.field === 'customer')).toBe(false);
  });

  it('lists a mapping per path and API, with the depth for the indent', () => {
    const rows = mappingRows(snap);
    const price = rows.find((r) => r.field === 'lines[].price.amount' && r.apiId === 'shopify');
    expect(price).toMatchObject({ depth: 2, kind: 'derived', paths: ['line_items[].price'] });
    expect(
      rows.find((r) => r.field === 'customer.email' && r.apiId === 'woocommerce'),
    ).toBeUndefined(); // unsupported
  });
});

describe('nested fields: the table', () => {
  async function table() {
    const r = renderApp(`/models/${NESTED}?view=table`);
    await screen.findByRole('table', { name: /How each API fills each field/ });
    return r;
  }
  /** The field names of the table rows (the toggle's glyph is not part of the name). */
  const names = () =>
    within(screen.getByRole('table'))
      .getAllByRole('rowheader')
      .map((h) =>
        [...(h.querySelector('.mtable-name')?.childNodes ?? [])]
          .filter((n) => n.nodeType === Node.TEXT_NODE)
          .map((n) => n.textContent)
          .join('')
          .trim(),
      );

  it('shows containers with their children indented under them, and the canonical path of a sub-field', async () => {
    await table();
    expect(names()).toEqual([
      'id',
      'customer',
      'name',
      'email',
      'lines',
      'sku',
      'price',
      'amount',
      'currency',
    ]);
    expect(screen.getByText('lines[].price.amount')).toBeInTheDocument();
    const amount = screen.getByText('lines[].price.amount').closest('th') as HTMLElement;
    const top = screen.getByRole('rowheader', { name: /^id/ });
    expect(parseInt(amount.style.paddingLeft, 10)).toBeGreaterThan(
      parseInt(top.style.paddingLeft || '0', 10),
    );
    // a container with no sources of its own says where it comes from
    const customer = screen
      .getByRole('button', { name: 'Collapse customer' })
      .closest('tr') as HTMLElement;
    expect(within(customer).getAllByText('from its sub-fields').length).toBeGreaterThan(0);
    // the count is of leaves
    expect(screen.getByText('6 of 6 fields')).toBeInTheDocument();
  });

  it('collapses and expands a container (keyboard operable), and a container with its own sources stays a row', async () => {
    await table();
    const toggle = screen.getByRole('button', { name: 'Collapse lines' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(toggle);
    expect(names()).toEqual(['id', 'customer', 'name', 'email', 'lines']); // all of lines' sub-fields hidden
    expect(screen.getByRole('button', { name: 'Expand lines' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    screen.getByRole('button', { name: 'Expand lines' }).focus();
    await userEvent.keyboard('{Enter}');
    expect(names()).toHaveLength(9);
  });

  it('a filter keeps the parents of the matching fields, open', async () => {
    await table();
    await userEvent.click(screen.getByRole('button', { name: 'Collapse lines' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Filter fields' }), 'amount');
    expect(names()).toEqual(['lines', 'price', 'amount']); // shown in place although "lines" was collapsed
    expect(screen.getByText('1 of 6 fields')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse lines' })).toBeDisabled(); // while filtering everything is open
  });

  it('"only fields with gaps" keeps the sub-field that has one with its parents', async () => {
    await table();
    await userEvent.click(screen.getByRole('button', { name: 'Only fields with gaps' }));
    expect(names()).toContain('email'); // WooCommerce has no customer.email
    expect(names()).toContain('customer');
    expect(names()).not.toContain('id');
  });
});

describe('nested fields: the control box and the detail', () => {
  it('lists the mappings by canonical path, indented; picking one shows it and keeps its path in the URL', async () => {
    const { router } = renderApp(`/models/${NESTED}?view=graph&scope=all`);
    const list = await screen.findByRole('listbox', { name: 'Mappings' });
    const row = within(list).getByRole('option', { name: /lines\[\]\.price\.amount ← Shopify/ });
    expect(parseInt(row.style.paddingLeft, 10)).toBeGreaterThan(
      parseInt(within(list).getByRole('option', { name: /^id ← Shopify/ }).style.paddingLeft, 10),
    );
    await userEvent.click(row);
    const detail = screen.getByRole('region', { name: 'Mapping detail' });
    expect(
      within(detail).getByRole('heading', { name: 'lines[].price.amount ← Shopify' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(search(router).get('field')).toBe('lines[].price.amount'));
    expect(search(router).get('api')).toBe('shopify');
  });

  it('the name filter matches a path fragment of a nested field', async () => {
    renderApp(`/models/${NESTED}?view=graph&scope=all`);
    await userEvent.type(await screen.findByRole('searchbox', { name: 'Filter by name' }), 'price');
    const list = screen.getByRole('listbox', { name: 'Mappings' });
    await waitFor(() => expect(within(list).getAllByRole('option').length).toBeLessThan(10));
    for (const o of within(list).getAllByRole('option'))
      expect(o.querySelector('.wb-row-name')?.textContent).toMatch(/price|line_items/);
  });

  it('"Selected field" shows only that mapping, not its sub-fields', async () => {
    renderApp(`/models/${NESTED}?view=graph&scope=field&field=lines&api=shopify`);
    await screen.findByRole('group', { name: /Mapping graph/ });
    await waitFor(() =>
      expect(document.querySelectorAll('.react-flow__node-canonical').length).toBe(1),
    );
    expect(document.querySelector('.react-flow__node-canonical')?.textContent).toContain('lines');
  });

  it('a link to a field that does not exist falls back to the default mapping', async () => {
    renderApp(`/models/${NESTED}?view=graph&scope=all&field=nope&api=shopify`);
    const detail = await screen.findByRole('region', { name: 'Mapping detail' });
    expect(within(detail).getByRole('heading')).toHaveTextContent(' ← ');
  });
});

describe('nested fields in the page header', () => {
  it('the field chip counts leaves, the way the server counts coverage', async () => {
    renderApp(`/models/${NESTED}`);
    expect(await screen.findByText('6 fields')).toBeInTheDocument();
    expect(screen.getByText('Order with lines', { selector: 'h1' })).toBeInTheDocument();
    expect(countLeaves(nestedSnapshot)).toBe(6);
  });
});
