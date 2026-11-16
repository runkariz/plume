import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import type { Impact } from '@/api/types';
import { inventorySnapshot, order40Snapshot, productSnapshot } from '@/mocks/modelData';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { pollConfig } from './GenerateSession';

const staleModel = `/models/${order40Snapshot.id}`;

// These tests are about a server that does NOT send `impact` (the stale mark is the fallback): the mock's models carry
// one, so it is taken off for them (impact.test.tsx covers a server that sends it).
const impacts = new Map<string, Impact | null | undefined>();
const WITHOUT = [order40Snapshot, inventorySnapshot, productSnapshot];

beforeEach(() => {
  pollConfig.ms = 40;
  for (const m of WITHOUT) {
    impacts.set(m.id, m.impact);
    delete m.impact;
  }
  server.use(...createHandlers(TEST_API_BASE)); // fresh mock backend per test
});
afterEach(() => {
  pollConfig.ms = 3000;
  for (const m of WITHOUT) m.impact = impacts.get(m.id);
});

describe('a stale model says so', () => {
  it('shows a chip naming the APIs whose docs changed, and a banner with the builds', async () => {
    renderApp(staleModel);
    expect(
      await screen.findByText('Stale: built on older docs of Shopify, WooCommerce'),
    ).toBeInTheDocument();
    expect(screen.getByText('This model is built on older docs')).toBeInTheDocument();
    expect(
      screen.getByText(/The docs of Shopify, WooCommerce changed after it was built/),
    ).toBeInTheDocument();
    // the pinned and the current build of each stale API
    expect(screen.getByText('b-e9f58eb5a9cb')).toBeInTheDocument();
    expect(screen.getByText('b-91c706474d71')).toBeInTheDocument();
    expect(screen.queryByText(/older docs of Mirakl/)).not.toBeInTheDocument();
  });

  it('puts the details in the chip tooltip', async () => {
    renderApp(staleModel);
    const chip = await screen.findByText('Stale: built on older docs of Shopify, WooCommerce');
    expect(chip.parentElement?.getAttribute('title')).toContain(
      'Shopify: built on b-e9f58eb5a9cb, now b-91c706474d71',
    );
  });

  it('a current model has no stale mark and no Regenerate', async () => {
    renderApp('/models/snap_8f3a21');
    await screen.findByRole('heading', { level: 1, name: 'Inventory' });
    expect(screen.queryByText(/Stale/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Regenerate' })).not.toBeInTheDocument();
  });

  it('Regenerate opens a new generation session for the same concept and APIs', async () => {
    renderApp(staleModel);
    const regenerate = await screen.findByRole('link', { name: 'Regenerate' });
    expect(regenerate).toHaveAttribute(
      'href',
      '/models/suggest?apis=shopify,woocommerce,mirakl&regenerate=Order',
    );
    await userEvent.click(regenerate);
    const panel = await screen.findByRole('region', { name: 'Generation session' });
    expect(
      within(panel).getByRole('heading', { name: 'Waiting for a draft: Order' }),
    ).toBeInTheDocument();
    // the old, stale Order model must not be mistaken for the new one: the page stays on the session
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getByRole('region', { name: 'Generation session' })).toBeInTheDocument();
    expect(screen.queryByText('This model is built on older docs')).not.toBeInTheDocument();
    // a current model arrives (what Claude does through the maintainer MCP): the page opens it
    const prompt = within(panel).getByLabelText('Prompt for Claude').textContent ?? '';
    const sessionId = /get_model_context\("(s-mock\d+)"\)/.exec(prompt)?.[1] ?? '';
    const { testClient } = await import('@/test/render');
    await testClient().submitModelDraft(sessionId, { name: 'Order', fields: [{ name: 'sku' }] }); // unlisted: no token
    const h1 = await screen.findByRole('heading', { level: 1, name: 'Order' }, { timeout: 3000 });
    expect(h1).toBeInTheDocument();
    expect(screen.queryByText(/Stale/)).not.toBeInTheDocument();
  });

  it('says so when the concept to regenerate is not suggested any more', async () => {
    renderApp('/models/suggest?apis=shopify,woocommerce,mirakl&regenerate=Nonexistent');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '“Nonexistent” is not suggested for these APIs any more',
    );
    expect(screen.queryByRole('region', { name: 'Generation session' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate Order' })).toBeEnabled();
  });

  it('does not start a session on its own without ?regenerate', async () => {
    renderApp('/models/suggest?apis=shopify,woocommerce,mirakl');
    await screen.findByRole('button', { name: 'Generate Order' });
    expect(screen.queryByRole('region', { name: 'Generation session' })).not.toBeInTheDocument();
  });
});

describe('model lists carry the stale mark', () => {
  it('the models page lists existing models, stale ones marked, current ones too', async () => {
    renderApp('/models');
    const list = await screen.findByRole('region', { name: 'Official models' });
    const order = within(list).getByRole('link', { name: 'Order' }).closest('li') as HTMLElement;
    expect(within(order).getByText('Stale')).toBeInTheDocument();
    expect(within(order).getByText('Shopify · WooCommerce · Mirakl')).toBeInTheDocument();
    expect(within(order).getByText('Stale').parentElement?.getAttribute('title')).toContain(
      'b-91c706474d71',
    );
    const inventory = within(list)
      .getByRole('link', { name: 'Inventory' })
      .closest('li') as HTMLElement;
    expect(within(inventory).getByText('Official')).toBeInTheDocument();
    await userEvent.click(within(list).getByRole('link', { name: 'Order' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Order' })).toBeInTheDocument();
  });

  it('the API page lists the models built from it', async () => {
    renderApp('/apis/shopify');
    const list = await screen.findByRole('region', { name: 'Canonical models' });
    // released (official) models only: the unlisted and the unreleased ones of the mock never show
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.querySelector('b')?.textContent),
    ).toEqual(
      expect.arrayContaining(['Inventory', 'Order', 'Product', 'Order (Shopify + WooCommerce)']),
    );
    // one official model per concept and API set: the Order over all three APIs, and the one over two
    expect(within(list).getAllByRole('listitem')).toHaveLength(4);
    expect(within(list).queryByText('Return')).not.toBeInTheDocument();
    expect(within(list).queryByText('Inventory, with a returns count')).not.toBeInTheDocument();
    // the stale Order and the stale Order over Shopify + WooCommerce
    expect(within(list).getAllByText('Stale')).toHaveLength(2);
  });

  it('shows no list when there are no models, and no error when the list cannot be loaded', async () => {
    server.use(http.get(`${TEST_API_BASE}/v1/models`, () => HttpResponse.json({ items: [] })));
    const { unmount } = renderApp('/models');
    await screen.findByRole('checkbox', { name: /Shopify/ });
    expect(screen.queryByRole('region', { name: 'Official models' })).not.toBeInTheDocument();
    unmount();
    server.use(
      http.get(`${TEST_API_BASE}/v1/models`, () =>
        HttpResponse.json({ error: 'x', message: 'down' }, { status: 500 }),
      ),
    );
    renderApp('/models');
    await screen.findByRole('checkbox', { name: /Shopify/ });
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.queryByRole('region', { name: 'Official models' })).not.toBeInTheDocument();
  });
});
