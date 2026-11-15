import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { authStore } from '@/app/authStore';
import { renderApp, testClient } from '@/test/render';
import { createHandlers } from '@/mocks/handlers';
import { server, TEST_API_BASE } from '@/test/server';
import { pollConfig } from './GenerateSession';

const url = '/models/suggest?apis=shopify,woocommerce,mirakl';

async function openSession() {
  renderApp(url);
  // "Order" has no snapshot yet in the mock: the server opens a session and waits for a draft
  await userEvent.click(await screen.findByRole('button', { name: 'Generate Order' }));
  return screen.findByRole('region', { name: 'Generation session' });
}

beforeEach(() => {
  pollConfig.ms = 40;
  // a fresh mock backend per test: snapshots created by one test must not leak into the next
  server.use(...createHandlers(TEST_API_BASE));
});
afterEach(() => {
  pollConfig.ms = 3000;
});

describe('Generate: waiting for a draft (P5 sessions)', () => {
  it('opens a session panel with the prompt for Claude and the pinned builds', async () => {
    const panel = await openSession();
    expect(
      within(panel).getByRole('heading', { name: 'Waiting for a draft: Order' }),
    ).toBeInTheDocument();
    expect(within(panel).getByLabelText('Prompt for Claude')).toHaveTextContent(
      /get_model_context\("s-mock\d+"\).*submit_model_draft/,
    );
    const pinned = within(panel).getByRole('list', { name: 'Pinned builds' });
    expect(within(pinned).getAllByRole('listitem')).toHaveLength(3);
    expect(within(pinned).getAllByText('b-6ff6063a275d')).toHaveLength(3);
    expect(within(panel).getByText('Checking for the new model')).toBeInTheDocument();
    // the other Generate buttons wait until this session is closed
    expect(screen.getByRole('button', { name: 'Generate Product' })).toBeDisabled();
  });

  it('shows a copy-ready connect line for the maintainer connector, with a token placeholder', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    authStore.signIn('pl_secret_do_not_print', 'maintainer');
    const panel = await openSession();
    const line = within(panel).getByLabelText('Command to add the maintainer connector');
    expect(line).toHaveTextContent(
      'claude mcp add --transport http plume-maintainer http://127.0.0.1:18481/maintainer/mcp --header "Authorization: Bearer <your maintainer token>"',
    );
    expect(line.textContent).not.toContain('pl_secret_do_not_print');
    await userEvent.click(within(panel).getByRole('button', { name: 'Copy command' }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('plume-maintainer')),
    );
    expect(writeText.mock.calls[0]?.[0]).not.toContain('pl_secret_do_not_print');
    expect(await within(panel).findByText(/Command copied/)).toBeInTheDocument();
  });

  it('copies the prompt', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const panel = await openSession();
    await userEvent.click(within(panel).getByRole('button', { name: 'Copy prompt' }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('get_model_context')),
    );
    expect(
      await within(panel).findByText('Prompt copied: paste it into Claude'),
    ).toBeInTheDocument();
  });

  it('shows the evidence index on demand, then the fields page by page', async () => {
    const panel = await openSession();
    expect(within(panel).queryByRole('region', { name: 'Evidence pack' })).not.toBeInTheDocument();
    await userEvent.click(
      within(panel).getByRole('button', { name: 'See what Plume gives Claude' }),
    );
    const pack = await within(panel).findByRole('region', { name: 'Evidence pack' });
    // compact index: documents with field counts, one section per API
    const shopify = within(pack).getByRole('region', { name: 'Evidence for Shopify' });
    expect(within(shopify).getByText('Order')).toBeInTheDocument();
    expect(within(shopify).getByText('3 fields')).toBeInTheDocument();
    expect(within(shopify).getByText('GET /api/{version}/orders')).toBeInTheDocument();
    expect(within(shopify).getByText('partial schema')).toBeInTheDocument();
    expect(within(shopify).queryByRole('table')).not.toBeInTheDocument();
    // the fields come on request, one page at a time
    await userEvent.click(within(pack).getByRole('button', { name: /^Show Shopify fields/ }));
    expect(await within(shopify).findByText('3 of 5 fields shown')).toBeInTheDocument();
    const orderTable = within(shopify).getByRole('table', { name: 'Fields of Order' });
    expect(within(orderTable).getByText('number')).toBeInTheDocument();
    expect(within(orderTable).getAllByText('required')).toHaveLength(2);
    expect(within(shopify).queryByText('orders[].id')).not.toBeInTheDocument();
    await userEvent.click(within(shopify).getByRole('button', { name: 'Load more fields' }));
    expect(await within(shopify).findByText('5 of 5 fields shown')).toBeInTheDocument();
    expect(within(shopify).getByText('orders[].id')).toBeInTheDocument();
    expect(
      within(shopify).queryByRole('button', { name: 'Load more fields' }),
    ).not.toBeInTheDocument();
    // the draft format stays one click away
    await userEvent.click(within(pack).getByText('Draft format'));
    expect(within(pack).getByLabelText('Draft format')).toHaveTextContent('"fields"');
    await userEvent.click(within(panel).getByRole('button', { name: 'Hide the evidence pack' }));
    expect(within(panel).queryByRole('region', { name: 'Evidence pack' })).not.toBeInTheDocument();
  });

  it('shows an error when a page of fields cannot be loaded, and retries', async () => {
    server.use(
      http.get(
        `${TEST_API_BASE}/v1/models/sessions/:id/evidence`,
        () => HttpResponse.json({ error: 'bad_request', message: 'index busy' }, { status: 503 }),
        { once: true },
      ),
    );
    const panel = await openSession();
    await userEvent.click(
      within(panel).getByRole('button', { name: 'See what Plume gives Claude' }),
    );
    const pack = await within(panel).findByRole('region', { name: 'Evidence pack' });
    await userEvent.click(within(pack).getByRole('button', { name: /^Show Shopify fields/ }));
    const alert = await within(pack).findByRole('alert');
    expect(alert).toHaveTextContent('index busy');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await within(pack).findByText('3 of 5 fields shown')).toBeInTheDocument();
  });

  it('asks signed-out visitors to sign in before pasting a draft', async () => {
    const panel = await openSession();
    expect(within(panel).getByText('Maintainers can paste a draft')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: 'Sign in as a maintainer' })).toHaveAttribute(
      'href',
      '/maintainer',
    );
    expect(within(panel).queryByLabelText('Draft JSON')).not.toBeInTheDocument();
  });

  it('can be cancelled', async () => {
    const panel = await openSession();
    await userEvent.click(within(panel).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('region', { name: 'Generation session' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate Product' })).toBeEnabled();
  });
});

describe('Generate: pasting a draft (maintainer)', () => {
  async function signedInPanel() {
    authStore.signIn('pl_ok', 'maintainer');
    return openSession();
  }
  const paste = async (panel: HTMLElement, text: string) => {
    const box = within(panel).getByLabelText('Draft JSON');
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste(text);
  };

  it('rejects text that is not JSON before calling the server', async () => {
    const panel = await signedInPanel();
    await paste(panel, '{ nope');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit draft' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent('That is not valid JSON');
  });

  it('shows the refusal issues with their codes and keeps the session open', async () => {
    const panel = await signedInPanel();
    await paste(panel, '{"name":"Order","fields":[{"name":"total"}],"refuse":"quote"}');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit draft' }));
    const alert = await within(panel).findByRole('alert');
    expect(alert).toHaveTextContent('The draft was refused, nothing was stored.');
    expect(within(alert).getByText('QUOTE_NOT_FOUND')).toBeInTheDocument();
    expect(within(alert).getByText('total / shopify')).toBeInTheDocument();
    expect(within(alert).getByText(/the quote is not in model:order/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Generation session' })).toBeInTheDocument();
  });

  it('shows a format issue for a draft without fields', async () => {
    const panel = await signedInPanel();
    await paste(panel, '{"name":"Order"}');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit draft' }));
    expect(await within(panel).findByText('INVALID_FORMAT')).toBeInTheDocument();
  });

  it('opens the stored model after an accepted draft', async () => {
    const panel = await signedInPanel();
    await paste(panel, '{"name":"Order","fields":[{"name":"sku"}]}');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit draft' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Order' })).toBeInTheDocument();
    expect(screen.getByText('Generated, unverified')).toBeInTheDocument();
  });

  it('tells the person to sign in again when the token is rejected', async () => {
    authStore.signIn('bad-token', 'maintainer');
    const panel = await openSession();
    await paste(panel, '{"name":"Order","fields":[{"name":"sku"}]}');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit draft' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent('Sign in again');
  });
});

describe('Generate: noticing a model created elsewhere (Claude over MCP)', () => {
  it('opens the model when a snapshot for this concept and these APIs appears', async () => {
    const panel = await openSession();
    const sessionId = /get_model_context\("(s-mock\d+)"\)/.exec(
      within(panel).getByLabelText('Prompt for Claude').textContent ?? '',
    )?.[1];
    expect(sessionId).toBeTruthy();
    // what Claude does through the maintainer MCP, here over HTTP with a maintainer token
    authStore.signIn('pl_claude', 'claude');
    await testClient().submitModelDraft(sessionId ?? '', {
      name: 'Order',
      fields: [{ name: 'sku' }],
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Order' }, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it('opens an existing model straight away when the server says ready', async () => {
    authStore.signIn('pl_claude', 'claude');
    const c = testClient();
    const apis = ['shopify', 'woocommerce', 'mirakl'];
    const first = await c.generateModel({ apis, concept: 'order' });
    expect(first.status).toBe('awaiting_draft');
    await c.submitModelDraft(first.sessionId, { name: 'Order', fields: [{ name: 'sku' }] });
    authStore.signOut();
    renderApp(url);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Order' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Order' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Generation session' })).not.toBeInTheDocument();
  });
});
