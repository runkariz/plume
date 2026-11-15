import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

describe('Pick the APIs', () => {
  it('shows loading, then the candidates with category counts', async () => {
    renderApp('/models');
    expect(screen.getByRole('status')).toHaveTextContent('Loading APIs');
    expect(await screen.findByRole('checkbox', { name: /Shopify Admin REST/ })).toBeInTheDocument();
    const group = screen.getByRole('group', { name: 'Filter by category' });
    expect(within(group).getByRole('button', { name: 'All · 6' })).toBeInTheDocument();
    expect(within(group).getByRole('button', { name: 'E-commerce · 4' })).toBeInTheDocument();
    expect(screen.queryByText('3 selected')).not.toBeInTheDocument();
  });

  it('selects APIs, shows the bar, needs two to continue, and clears', async () => {
    renderApp('/models');
    await userEvent.click(await screen.findByRole('checkbox', { name: /Shopify Admin REST/ }));
    const bar = screen.getByRole('region', { name: 'Selected APIs' });
    expect(within(bar).getByText('1 selected')).toBeInTheDocument();
    expect(within(bar).getByRole('button', { name: 'Suggest models →' })).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: /WooCommerce/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /Mirakl/ }));
    expect(within(bar).getByText('3 selected')).toBeInTheDocument();
    expect(within(bar).getByText('Shopify')).toBeInTheDocument();
    expect(within(bar).getByRole('button', { name: 'Suggest models →' })).toBeEnabled();
    await userEvent.click(within(bar).getByRole('button', { name: 'Clear' }));
    expect(screen.queryByRole('region', { name: 'Selected APIs' })).not.toBeInTheDocument();
  });

  it('filters by category', async () => {
    renderApp('/models');
    await screen.findByRole('checkbox', { name: /Stripe/ });
    await userEvent.click(screen.getByRole('button', { name: 'Payments · 1' }));
    expect(screen.queryByRole('checkbox', { name: /Shopify/ })).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Stripe/ })).toBeInTheDocument();
  });

  it('restores the selection from the URL (Change APIs)', async () => {
    renderApp('/models?apis=shopify,mirakl');
    await screen.findByRole('checkbox', { name: /Shopify/ });
    expect(screen.getByRole('checkbox', { name: /Shopify/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Mirakl/ })).toBeChecked();
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('shows empty and error states', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/candidates`, () => HttpResponse.json({ items: [] }), {
        once: true,
      }),
    );
    const { unmount } = renderApp('/models');
    expect(await screen.findByText('No APIs to model yet')).toBeInTheDocument();
    unmount();
    server.use(
      http.get(
        `${TEST_API_BASE}/v1/models/candidates`,
        () => HttpResponse.json({ detail: 'db down' }, { status: 503 }),
        {
          once: true,
        },
      ),
    );
    renderApp('/models');
    expect(await screen.findByRole('alert')).toHaveTextContent('db down');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('checkbox', { name: /Shopify/ })).toBeInTheDocument();
  });

  it('goes to the suggestions with the selected ids', async () => {
    renderApp('/models');
    for (const n of [/Shopify/, /WooCommerce/, /Mirakl/])
      await userEvent.click(await screen.findByRole('checkbox', { name: n }));
    await userEvent.click(screen.getByRole('button', { name: 'Suggest models →' }));
    expect(await screen.findByRole('heading', { name: 'Suggested models' })).toBeInTheDocument();
    expect(await screen.findByText('Inventory')).toBeInTheDocument();
  });
});

describe('Suggested models', () => {
  const url = '/models/suggest?apis=shopify,woocommerce,mirakl';

  it('lists the concepts with coverage, operations and difficulty', async () => {
    renderApp(url);
    expect(screen.getByRole('status')).toHaveTextContent('Looking across the APIs');
    expect(await screen.findByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByText('~7 likely fields')).toBeInTheDocument();
    const inv = screen
      .getByRole('heading', { name: 'Inventory' })
      .closest('article') as HTMLElement;
    expect(within(inv).getByLabelText('Shopify (derived)')).toBeInTheDocument();
    expect(within(inv).getByLabelText('WooCommerce')).toBeInTheDocument();
    expect(within(inv).getByText('read, write')).toBeInTheDocument();
    expect(within(inv).getByText('Derived in 2')).toBeInTheDocument();
    const cust = screen
      .getByRole('heading', { name: 'Customer' })
      .closest('article') as HTMLElement;
    expect(within(cust).getByLabelText('Mirakl (absent)')).toBeInTheDocument();
    expect(within(cust).getByText('Not in all 3')).toBeInTheDocument();
    expect(screen.getByText('Using Claude instead?')).toBeInTheDocument();
    expect(screen.getByText(/9 resources exist in only one API/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Change APIs' })).toHaveAttribute(
      'href',
      '/models?apis=shopify,woocommerce,mirakl',
    );
  });

  it('says so when nothing is left out of the suggestions', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/suggest`, async () => {
        const { sampleSuggestions } = await import('@/mocks/modelData');
        const r = sampleSuggestions(['shopify', 'woocommerce', 'mirakl']);
        return HttpResponse.json({ ...r, notModeled: { count: 0, summary: 'none' } });
      }),
    );
    renderApp(url);
    expect(await screen.findByText(/Every resource found in these APIs/)).toBeInTheDocument();
    expect(screen.queryByText(/0 none/)).not.toBeInTheDocument();
  });

  it('filters: in all 3 APIs, can write', async () => {
    renderApp(url);
    await screen.findByRole('heading', { name: 'Customer' });
    await userEvent.click(screen.getByRole('radio', { name: 'In all 3 APIs' }));
    expect(screen.queryByRole('heading', { name: 'Customer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Location' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Product' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Can write' }));
    expect(screen.queryByRole('heading', { name: 'Customer' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Shipment' })).toBeInTheDocument();
  });

  it('asks for two APIs when the selection is too small', () => {
    renderApp('/models/suggest?apis=shopify');
    expect(screen.getByText('Pick at least two APIs')).toBeInTheDocument();
  });

  it('shows an empty state when no concepts are shared', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/suggest`, () =>
        HttpResponse.json({ apis: [], concepts: [], notModeled: { count: 0, summary: '' } }),
      ),
    );
    renderApp(url);
    expect(await screen.findByText('No shared concepts found')).toBeInTheDocument();
  });

  it('shows an error and retries', async () => {
    server.use(
      http.post(
        `${TEST_API_BASE}/v1/models/suggest`,
        () => HttpResponse.json({ detail: 'index offline' }, { status: 500 }),
        {
          once: true,
        },
      ),
    );
    renderApp(url);
    expect(await screen.findByRole('alert')).toHaveTextContent('index offline');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
  });

  it('Generate opens the mapping view', async () => {
    renderApp(url);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Inventory' }));
    expect(await screen.findByText('Generated, unverified')).toBeInTheDocument();
  });

  it('shows the busy state and disables the other Generate buttons while generating', async () => {
    let release: () => void = () => undefined;
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/generate`, async () => {
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json({
          sessionId: 's-1',
          status: 'ready',
          snapshotId: 'snap_8f3a21',
          inputs: [],
          contextUrl: '/v1/models/sessions/s-1/context',
          claudePrompt: '',
          mcpUrl: '',
        });
      }),
    );
    renderApp(url);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Inventory' }));
    expect(screen.getByRole('button', { name: 'Generating Inventory' })).toHaveAttribute(
      'aria-busy',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Generate Product' })).toBeDisabled();
    release();
    expect(await screen.findByText('Generated, unverified')).toBeInTheDocument();
  });

  it('shows a clear message when generation needs sign-in', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/generate`, () =>
        HttpResponse.json({ detail: 'nope' }, { status: 401 }),
      ),
    );
    renderApp(url);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Product' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign in again');
    expect(screen.getByRole('button', { name: 'Generate Product' })).toBeEnabled();
  });
});

describe('Model view', () => {
  it('shows loading, then the header, graph nodes, open questions and coverage', async () => {
    renderApp('/models/snap_8f3a21');
    expect(await screen.findByRole('heading', { level: 1, name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByText('Generated, unverified')).toBeInTheDocument();
    expect(screen.getByText('3 APIs')).toBeInTheDocument();
    expect(screen.getByText('7 fields')).toBeInTheDocument();
    expect(screen.getByText('snapshot snap_8f3a21')).toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole('link', {
        name: 'Models',
      }),
    ).toHaveAttribute('href', '/models');
    // graph nodes (the canonical fields and the API fields are rendered by React Flow)
    expect(await screen.findAllByText('quantity_available')).not.toHaveLength(0);
    expect(screen.getAllByText('variants[].sku').length).toBeGreaterThan(0);
    // open questions with bold spans
    const oq = screen
      .getByRole('heading', { name: 'Open questions' })
      .closest('div') as HTMLElement;
    expect(within(oq).getByText('available').tagName).toBe('STRONG');
    expect(within(oq).getByText(/Shopify exposes available per location/)).toBeInTheDocument();
    // coverage
    expect(screen.getByLabelText('Mirakl: 4 of 7 fields')).toBeInTheDocument();
    expect(screen.getByText('Generated by Claude through Plume · prompt v1')).toBeInTheDocument();
  });

  it('shows a loading state while the snapshot loads', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, async () => {
        await delay(150);
        return HttpResponse.json({ detail: 'late' }, { status: 404 });
      }),
    );
    renderApp('/models/snap_8f3a21');
    expect(await screen.findByRole('status')).toHaveTextContent('Loading the model');
    expect(await screen.findByRole('alert')).toHaveTextContent('Model not found');
  });

  it('opens on the first derived mapping and shows fetch, join, evidence and the citation check', async () => {
    renderApp('/models/snap_8f3a21');
    expect(
      await screen.findByRole('heading', { name: 'quantity_available ← Shopify' }),
    ).toBeInTheDocument();
    expect(screen.getByText('derived: join')).toBeInTheDocument();
    expect(screen.getByText(/GET \/admin\/api\/2026-10\/locations/)).toBeInTheDocument();
    expect(
      screen.getByText(/variants\[\]\.inventory_item_id = inventory_levels/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Total available stock quantity across all locations/),
    ).toBeInTheDocument();
    expect(screen.getByText('All 14 cited paths found in the pinned builds')).toBeInTheDocument();
  });

  it('switches the detail with the mapping list (keyboard alternative to clicking the graph)', async () => {
    renderApp('/models/snap_8f3a21');
    const pick = await screen.findByRole('combobox', { name: 'Mapping' });
    await userEvent.selectOptions(pick, 'sku|mirakl');
    expect(screen.getByRole('heading', { name: 'sku ← Mirakl' })).toBeInTheDocument();
    expect(screen.getByText('direct', { selector: '.chip' })).toBeInTheDocument();
    expect(screen.queryByText(/GET \/admin/)).not.toBeInTheDocument();
  });

  it('filters a long mapping list and keeps the selected mapping visible', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, async () => {
        const { inventorySnapshot } = await import('@/mocks/modelData');
        const base = inventorySnapshot.fields[2];
        if (!base) throw new Error('fixture');
        // 12 extra fields: more than 12 mappings in total, so the filter box appears
        const extra = Array.from({ length: 12 }, (_, i) => ({ ...base, name: `extra_${i}` }));
        return HttpResponse.json({
          ...inventorySnapshot,
          fields: [...inventorySnapshot.fields, ...extra],
        });
      }),
    );
    renderApp('/models/snap_8f3a21');
    // 19 fields: a big model opens as a table; the Mapping list belongs to the graph view
    await userEvent.click(await screen.findByRole('radio', { name: 'Graph' }));
    const filter = await screen.findByRole('searchbox', { name: 'Filter mappings' });
    const total = screen
      .getByRole('combobox', { name: 'Mapping' })
      .querySelectorAll('option').length;
    expect(total).toBeGreaterThan(12);
    await userEvent.type(filter, 'extra_3');
    const options = screen.getByRole('combobox', { name: 'Mapping' }).querySelectorAll('option');
    // the matching mappings of extra_3 (3 APIs) plus the currently selected mapping, which stays visible
    expect(options.length).toBeLessThan(total);
    expect([...options].some((o) => o.textContent?.startsWith('extra_3'))).toBe(true);
    expect([...options].some((o) => o.textContent === 'quantity_available ← Shopify')).toBe(true);
    expect(
      screen.getByText(new RegExp(`${options.length} of ${total} mappings`)),
    ).toBeInTheDocument();
  });

  it('does not show the filter for a small model', async () => {
    renderApp('/models/snap_8f3a21');
    await screen.findByRole('combobox', { name: 'Mapping' });
    expect(screen.queryByRole('searchbox', { name: 'Filter mappings' })).not.toBeInTheDocument();
  });

  it('reports dropped citations', async () => {
    renderApp('/models/snap_prod01');
    expect(
      await screen.findByText(/1 of 6 cited paths were not found and were dropped: product_title/),
    ).toBeInTheDocument();
    expect(screen.getByText('No open questions.')).toBeInTheDocument();
  });

  it('copies the prompt for Claude and links to Claude', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderApp('/models/snap_8f3a21');
    await userEvent.click(await screen.findByRole('button', { name: 'Copy for Claude' }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(writeText.mock.calls[0]?.[0]).toContain('get_snapshot with id "snap_8f3a21"');
    expect(await screen.findByText('Prompt copied: paste it into Claude')).toBeInTheDocument();
    const open = screen.getByRole('link', { name: 'Open in Claude' });
    expect(open).toHaveAttribute('href', 'https://claude.ai/new');
    expect(open).toHaveAttribute('rel', 'noreferrer');
    // "Open in Claude" also copies the prompt, because the new chat cannot be pre-filled
    writeText.mockClear();
    await userEvent.click(open);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  });

  it('says so when copying fails', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    renderApp('/models/snap_8f3a21');
    await userEvent.click(await screen.findByRole('button', { name: 'Copy for Claude' }));
    expect(await screen.findByText(/Copy failed/)).toBeInTheDocument();
  });

  it('shows not found and a generic error', async () => {
    const { unmount } = renderApp('/models/snap_nope');
    expect(await screen.findByRole('alert')).toHaveTextContent('Model not found');
    unmount();
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderApp('/models/snap_8f3a21');
    expect(await screen.findByText('Could not load this model')).toBeInTheDocument();
  });
});
