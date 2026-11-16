import { render, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { ImpactChip } from '@/components/ImpactChip';
import { impactLine } from '@/lib/impact';
import { createHandlers } from '@/mocks/handlers';
import {
  inventorySnapshot,
  nestedSnapshot,
  order40Snapshot,
  productSnapshot,
} from '@/mocks/modelData';
import { SET_OFFICIAL } from '@/mocks/setStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
});
afterEach(() => authStore.signOut());

describe('the words of an impact', () => {
  it('says what the server says, quietly when current, never "unaffected" when unknown', () => {
    expect(impactLine({ status: 'affected', affectedCount: 3, breakingCount: 1 })?.title).toBe(
      '3 mappings affected (1 breaking)',
    );
    expect(impactLine({ status: 'affected', affectedCount: 1, breakingCount: 0 })?.title).toBe(
      '1 mapping affected',
    );
    expect(
      impactLine({ status: 'updated_unaffected', affectedCount: 0, breakingCount: 0 })?.title,
    ).toBe('Docs updated, your mappings are unaffected');
    expect(impactLine({ status: 'unknown', affectedCount: 0, breakingCount: 0 })?.title).toBe(
      'Not checked against newer docs',
    );
    expect(
      impactLine({ status: 'unknown', affectedCount: 0, breakingCount: 0 })?.title,
    ).not.toMatch(/unaffected/);
    expect(impactLine({ status: 'current', affectedCount: 0, breakingCount: 0 })).toBeNull();
    expect(impactLine(null)).toBeNull();
    expect(impactLine(undefined)).toBeNull();
  });
  it('a chip carries text and a glyph, and nothing when quiet or absent', () => {
    const { container, rerender } = render(
      <ImpactChip impact={{ status: 'affected', affectedCount: 2, breakingCount: 1 }} />,
    );
    expect(container).toHaveTextContent('⚠ 2 affected (1 breaking)');
    rerender(<ImpactChip impact={{ status: 'current', affectedCount: 0, breakingCount: 0 }} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ImpactChip impact={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('lists', () => {
  it('the models page shows the impact chip per model instead of the stale mark', async () => {
    renderApp('/models');
    const list = await screen.findByRole('region', { name: 'Official models' });
    const order = within(list).getByRole('link', { name: 'Order' }).closest('li') as HTMLElement;
    expect(order).toHaveTextContent('2 affected (1 breaking)');
    expect(within(order).queryByText('Stale')).not.toBeInTheDocument();
    const inventory = within(list)
      .getByRole('link', { name: 'Inventory' })
      .closest('li') as HTMLElement;
    expect(inventory).toHaveTextContent('Docs updated, unaffected');
    // current is quiet
    const product = within(list)
      .getByRole('link', { name: 'Product' })
      .closest('li') as HTMLElement;
    expect(product).not.toHaveTextContent(/affected|Docs updated|Not checked|Stale/);
  });
  it("the sets list shows the set's impact chip", async () => {
    renderApp('/models');
    const list = await screen.findByRole('region', { name: 'Official model sets' });
    const li = within(list).getByRole('link', { name: 'Shop' }).closest('li') as HTMLElement;
    expect(li).toHaveTextContent('3 affected (1 breaking)');
    expect(within(li).queryByText('Stale')).not.toBeInTheDocument();
  });
});

describe('a model page', () => {
  it('leads with how many mappings are affected, lists them linked to the mapping, with the vendor page', async () => {
    renderApp(`/models/${order40Snapshot.id}`);
    const banner = await screen.findByTestId('impact-banner');
    expect(banner).toHaveTextContent('2 mappings affected (1 breaking)');
    // the old blanket stale banner is replaced
    expect(screen.queryByText('This model is built on older docs')).not.toBeInTheDocument();
    const rows = await within(banner).findByRole('list', { name: 'Affected mappings' });
    const items = within(rows).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    // breaking first, with the word
    expect(items[0]).toHaveTextContent('Breaking');
    const link = within(items[0] as HTMLElement).getAllByRole('link')[0] as HTMLElement;
    expect(link.getAttribute('href')).toMatch(/\?.*field=.*&api=shopify/);
    expect(
      within(items[0] as HTMLElement).getByRole('link', { name: 'Vendor page' }),
    ).toHaveAttribute('target', '_blank');
  });
  it('Regenerate is for maintainers (an official model of the public)', async () => {
    renderApp(`/models/${order40Snapshot.id}`);
    await screen.findByTestId('impact-banner');
    expect(screen.queryByRole('link', { name: 'Regenerate' })).not.toBeInTheDocument();
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(`/models/${order40Snapshot.id}`);
    expect((await screen.findAllByRole('link', { name: 'Regenerate' })).length).toBeGreaterThan(0);
  });
  it('updated but unaffected says so; current has no banner; unknown never says unaffected', async () => {
    const a = renderApp(`/models/${inventorySnapshot.id}`);
    expect(await screen.findByTestId('impact-banner')).toHaveTextContent(
      'Docs updated, your mappings are unaffected',
    );
    expect(screen.queryByRole('link', { name: 'Regenerate' })).not.toBeInTheDocument();
    a.unmount();
    const b = renderApp(`/models/${productSnapshot.id}`);
    await screen.findByRole('heading', { level: 1, name: 'Product' });
    expect(screen.queryByTestId('impact-banner')).not.toBeInTheDocument();
    b.unmount();
    renderApp(`/models/${nestedSnapshot.id}`);
    const banner = await screen.findByTestId('impact-banner');
    expect(banner).toHaveTextContent('Not checked against newer docs');
    expect(banner).not.toHaveTextContent(/unaffected/);
  });
  it('says so when the affected rows cannot be loaded, and keeps the headline', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id/impact`, () =>
        HttpResponse.json({ error: 'x', message: 'down' }, { status: 500 }),
      ),
    );
    renderApp(`/models/${order40Snapshot.id}`);
    const banner = await screen.findByTestId('impact-banner');
    expect(banner).toHaveTextContent('2 mappings affected (1 breaking)');
    await waitFor(() => expect(banner).toHaveTextContent('could not be loaded'));
  });
  it('a server that sends no impact keeps the stale mark', async () => {
    const saved = order40Snapshot.impact;
    delete order40Snapshot.impact;
    try {
      server.use(...createHandlers(TEST_API_BASE));
      renderApp(`/models/${order40Snapshot.id}`);
      expect(await screen.findByText('This model is built on older docs')).toBeInTheDocument();
      expect(screen.queryByTestId('impact-banner')).not.toBeInTheDocument();
    } finally {
      order40Snapshot.impact = saved;
    }
  });
});

describe('a set page', () => {
  it("leads with the set's impact, each member with its own status, worst first, and the affected rows with their member", async () => {
    renderApp(`/model-sets/${SET_OFFICIAL}`);
    const banner = await screen.findByTestId('impact-banner');
    expect(banner).toHaveTextContent('3 mappings affected (1 breaking)');
    const members = within(banner).getByRole('list', { name: 'Impact per model' });
    const rows = within(members)
      .getAllByRole('listitem')
      .map((li) => li.textContent ?? '');
    expect(rows[0]).toContain('Order');
    expect(rows[0]).toContain('3 affected');
    expect(rows[1]).toContain('Variant'); // unknown before updated_unaffected
    expect(rows[1]).toContain('Not checked against newer docs');
    expect(rows[2]).toContain('Product');
    expect(rows[2]).toContain('Docs updated, unaffected');
    const affected = await within(banner).findByRole('list', { name: 'Affected mappings' });
    expect(within(affected).getAllByRole('listitem').length).toBeGreaterThan(0);
    expect(affected).toHaveTextContent('Order:');
  });
});
