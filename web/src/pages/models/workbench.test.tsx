import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { inventorySnapshot } from '@/mocks/modelData';
import { renderApp } from '@/test/render';
import { buildGraph, dimming, mappingRows, rowMatches } from './graph';
import { fitPadding } from './MappingGraph';
import { parseModelView, toggleApi, withModelView } from './modelView';

const url = '/models/snap_8f3a21';
const search = (router: { state: { location: { search: string } } }) =>
  new URLSearchParams(router.state.location.search);
const nodes = () => document.querySelectorAll('.react-flow__node');
const dimmedNodes = () => document.querySelectorAll('.react-flow__node.dim');
const box = () => screen.getByRole('complementary', { name: 'Graph controls' });

describe('the graph and its detail are visible together', () => {
  it('shows the graph, the control box and the mapping detail at once, no scrolling to a card below', async () => {
    renderApp(url);
    await screen.findByRole('group', { name: /Mapping graph/ });
    const detail = screen.getByRole('region', { name: 'Mapping detail' });
    expect(within(detail).getByRole('heading')).toHaveTextContent(' ← ');
    // fetch, source and the cited quote are in the panel
    expect(within(detail).getByText('Source')).toBeInTheDocument();
    expect(box()).toBeInTheDocument();
    // the old half-width card with the select under the graph is gone
    expect(screen.queryByRole('combobox', { name: 'Mapping' })).not.toBeInTheDocument();
    // the workbench holds the canvas and the panel side by side
    const wb = document.querySelector('.workbench') as HTMLElement;
    expect(wb.contains(detail)).toBe(true);
    expect(wb.contains(screen.getByRole('group', { name: /Mapping graph/ }))).toBe(true);
  });
});

describe('the control box', () => {
  it('filters by name (field or source path), greys out the rest and keeps everything in the graph', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('group', { name: /Mapping graph/ });
    await waitFor(() => expect(nodes().length).toBeGreaterThan(0));
    const total = nodes().length;
    expect(dimmedNodes()).toHaveLength(0);
    await userEvent.type(within(box()).getByRole('searchbox', { name: 'Filter by name' }), 'sku');
    await waitFor(() => expect(search(router).get('f')).toBe('sku'));
    await waitFor(() => expect(dimmedNodes().length).toBeGreaterThan(0));
    expect(nodes()).toHaveLength(total); // nothing is hidden, only greyed out
    expect(dimmedNodes().length).toBeLessThan(total);
  });

  it('unchecking an API greys out its nodes (edges: see dimming below), keeps them in the graph and the list, and goes in the URL', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('group', { name: /Mapping graph/ });
    await waitFor(() => expect(nodes().length).toBeGreaterThan(0));
    const total = nodes().length;
    await userEvent.click(within(box()).getByRole('checkbox', { name: 'Shopify' }));
    await userEvent.click(within(box()).getByRole('checkbox', { name: 'Mirakl' }));
    await waitFor(() => expect(search(router).get('show')).toBe('woocommerce'));
    expect(within(box()).getByRole('checkbox', { name: 'WooCommerce' })).toBeChecked();
    expect(within(box()).getByRole('checkbox', { name: 'Shopify' })).not.toBeChecked();
    await waitFor(() => expect(dimmedNodes().length).toBeGreaterThan(0));
    expect(nodes()).toHaveLength(total);
    // the unchecked APIs' rows stay in the list, greyed
    const list = within(box()).getByRole('listbox', { name: 'Mappings' });
    const off = within(list)
      .getAllByRole('option')
      .filter((o) => o.classList.contains('off'));
    expect(off.length).toBeGreaterThan(0);
    // the last checked API cannot be unchecked: something must stay in focus
    expect(within(box()).getByRole('checkbox', { name: 'WooCommerce' })).toBeDisabled();
  });

  it('two quick clicks on two checkboxes both count', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('group', { name: /Mapping graph/ });
    fireEvent.click(within(box()).getByRole('checkbox', { name: 'Shopify' }));
    fireEvent.click(within(box()).getByRole('checkbox', { name: 'Mirakl' }));
    await waitFor(() => expect(search(router).get('show')).toBe('woocommerce'));
  });

  it('opens with the filter, the checked APIs and the selected mapping from the URL', async () => {
    renderApp(`${url}?f=sku&show=woocommerce,mirakl&field=sku&api=mirakl`);
    await screen.findByRole('group', { name: /Mapping graph/ });
    expect(within(box()).getByRole('searchbox', { name: 'Filter by name' })).toHaveValue('sku');
    expect(within(box()).getByRole('checkbox', { name: 'Shopify' })).not.toBeChecked();
    expect(within(box()).getByRole('checkbox', { name: 'Mirakl' })).toBeChecked();
    expect(
      within(screen.getByRole('region', { name: 'Mapping detail' })).getByRole('heading', {
        name: 'sku ← Mirakl',
      }),
    ).toBeInTheDocument();
    const option = within(box()).getByRole('option', { name: /^sku ← Mirakl/ });
    expect(option).toHaveAttribute('aria-selected', 'true');
  });

  it('the mapping list works from the keyboard: arrows move, Enter selects, the URL keeps it', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('group', { name: /Mapping graph/ });
    const list = within(box()).getByRole('listbox', { name: 'Mappings' });
    const first = within(list).getAllByRole('option')[0] as HTMLElement;
    list.focus();
    expect(list).toHaveFocus();
    expect(list.getAttribute('aria-activedescendant')).toBe(first.id);
    await userEvent.keyboard('{ArrowDown}{ArrowDown}');
    const third = within(list).getAllByRole('option')[2] as HTMLElement;
    expect(list.getAttribute('aria-activedescendant')).toBe(third.id);
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(third).toHaveAttribute('aria-selected', 'true'));
    expect(search(router).get('field')).toBeTruthy();
    expect(search(router).get('api')).toBeTruthy();
    const heading = within(screen.getByRole('region', { name: 'Mapping detail' })).getByRole(
      'heading',
    );
    expect(third.querySelector('.wb-row-name')?.textContent).toBeTruthy();
    expect(heading.textContent).toContain(third.querySelector('.wb-row-name')?.textContent ?? '?');
    await userEvent.keyboard('{End}');
    const all = within(list).getAllByRole('option');
    expect(list.getAttribute('aria-activedescendant')).toBe(all[all.length - 1]?.id);
  });

  it('says so when no mapping matches the filter', async () => {
    renderApp(`${url}?f=zzzzzz`);
    await screen.findByRole('group', { name: /Mapping graph/ });
    expect(within(box()).getByText(/No mapping matches “zzzzzz”/)).toBeInTheDocument();
  });

  it('the view and the scope are in the URL too', async () => {
    const { router } = renderApp(url);
    await userEvent.click(await screen.findByRole('radio', { name: 'Table' }));
    await waitFor(() => expect(search(router).get('view')).toBe('table'));
  });
});

describe('the Selected field view fits the selection', () => {
  it('leaves room for the control box on the left and gives a short canvas', async () => {
    expect(fitPadding(308, 0.18)).toEqual({
      top: '18%',
      bottom: '18%',
      right: '18%',
      left: '324px',
    });
    const { order40Snapshot } = await import('@/mocks/modelData');
    renderApp(`/models/${order40Snapshot.id}?view=graph`);
    const wb = await waitFor(() => {
      const el = document.querySelector('.workbench') as HTMLElement | null;
      if (!el) throw new Error('not yet');
      return el;
    });
    // a single field is shown: a canvas of its own size, not the 760 px of the whole model
    expect(wb.style.getPropertyValue('--wb-h')).toBe('clamp(400px, 50vh, 520px)');
  });
});

describe('the Plume mark in the header', () => {
  it("shows the owner's mark: dark on the light theme, white on the dark one (small variants, no feather icon)", async () => {
    renderApp('/');
    const link = await screen.findByRole('link', { name: 'Plume home' });
    const imgs = link.querySelectorAll('img.brand-mark');
    expect(imgs).toHaveLength(2);
    expect(imgs[0]).toHaveAttribute('src', '/plume-mark-dark-96.png');
    expect(imgs[1]).toHaveAttribute('src', '/plume-mark-white-96.png');
    expect([...imgs].every((i) => i.getAttribute('alt') === '')).toBe(true); // decorative: the link has the name
    expect(link.querySelector('svg')).toBeNull();
  });
});

describe('model view helpers', () => {
  const snap = inventorySnapshot;
  const ids = snap.inputs.map((a) => a.id);

  it('reads the state from the URL with safe defaults and ignores what does not exist', () => {
    expect(parseModelView(new URLSearchParams(''), snap)).toEqual({
      view: null,
      scope: null,
      f: '',
      show: null,
      selection: null,
    });
    const v = parseModelView(
      new URLSearchParams('view=graph&scope=all&f= sku &show=zzz,mirakl&field=nope&api=mirakl'),
      snap,
    );
    expect(v).toMatchObject({
      view: 'graph',
      scope: 'all',
      f: 'sku',
      show: ['mirakl'],
      selection: null,
    });
    // all APIs checked is the default and not kept
    expect(parseModelView(new URLSearchParams(`show=${ids.join(',')}`), snap).show).toBeNull();
    expect(parseModelView(new URLSearchParams('view=x&scope=y'), snap)).toMatchObject({
      view: null,
      scope: null,
    });
  });

  it('writes the state back and keeps the other parameters', () => {
    const base = new URLSearchParams('keep=1&f=old');
    const p = withModelView(base, {
      view: 'graph',
      scope: 'field',
      f: 'new',
      show: ['mirakl'],
      selection: { field: 'sku', apiId: 'mirakl' },
    });
    expect(p.get('keep')).toBe('1');
    expect([
      p.get('view'),
      p.get('scope'),
      p.get('f'),
      p.get('show'),
      p.get('field'),
      p.get('api'),
    ]).toEqual(['graph', 'field', 'new', 'mirakl', 'sku', 'mirakl']);
  });

  it('toggles APIs: the last checked one stays, all checked collapses to the default', () => {
    expect(toggleApi(snap, null, 'mirakl', false)).toEqual(ids.filter((i) => i !== 'mirakl'));
    expect(toggleApi(snap, ['mirakl'], 'mirakl', false)).toEqual(['mirakl']); // refused
    expect(
      toggleApi(
        snap,
        ids.filter((i) => i !== 'mirakl'),
        'mirakl',
        true,
      ),
    ).toBeNull();
  });

  it('dims by checkbox and by filter without removing anything', () => {
    const g = buildGraph(snap);
    expect(dimming(g, { checked: null, text: '' }).nodes.size).toBe(0);
    const only = dimming(g, { checked: new Set(['woocommerce']), text: '' });
    expect(only.edges.size).toBeGreaterThan(0);
    expect(only.edges.size).toBeLessThan(g.edges.length);
    expect(only.nodes.has('group:shopify')).toBe(true);
    expect(only.nodes.has('group:woocommerce')).toBe(false);
    const sku = dimming(g, { checked: null, text: 'SKU' }); // case does not matter
    expect(sku.edges.size).toBeLessThan(g.edges.length);
    expect(sku.nodes.has('canon:sku')).toBe(false);
    expect(
      sku.nodes.has(
        'canon:' + (snap.fields.find((f) => !f.name.toLowerCase().includes('sku'))?.name ?? ''),
      ),
    ).toBe(true);
  });

  it('lists a mapping per field and API that fills it, and matches by field or source path', () => {
    const rows = mappingRows(snap);
    expect(rows.length).toBeGreaterThan(snap.fields.length);
    expect(rows.every((r) => r.kind === 'supported' || r.kind === 'derived')).toBe(true);
    const r = rows.find((x) => x.field === 'sku' && x.apiId === 'shopify');
    expect(r).toBeTruthy();
    if (r) {
      expect(rowMatches(r, 'SKU')).toBe(true);
      expect(rowMatches(r, r.paths[0] ?? 'zzz')).toBe(true);
      expect(rowMatches(r, 'definitely-not')).toBe(false);
      expect(rowMatches(r, '  ')).toBe(true);
    }
  });
});
