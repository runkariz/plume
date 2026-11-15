import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { setPollConfig } from './SetCreate';

const url = '/models/related?apis=shopify,woocommerce&concept=Product';

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  setPollConfig.ms = 40;
  server.use(...createHandlers(TEST_API_BASE));
});
afterEach(() => {
  setPollConfig.ms = 3000;
  authStore.signOut();
});

const row = (name: string) => screen.getByRole('checkbox', { name }).closest('li') as HTMLElement;
/** The page has its data once the create bar is there (the heading shows the concept right away). */
const loaded = () => screen.findByRole('region', { name: 'Create a model set' });
const bar = () => screen.getByRole('region', { name: 'Create a model set' });

describe('Related concepts: what the docs connect to a concept', () => {
  it('lists them with how each API documents the connection, and the designs the docs support', async () => {
    renderApp(url);
    await loaded();
    expect(
      screen.getByRole('heading', { name: 'Concepts related to Product', level: 1 }),
    ).toBeInTheDocument();
    const list = screen.getByRole('list', { name: 'Related concepts' });
    expect(
      within(list)
        .getAllByRole('checkbox')
        .map((c) => c.id),
    ).toEqual(['related-variant', 'related-variation', 'related-image', 'related-lineitem']);
    const variant = row('Variant');
    expect(variant).toHaveTextContent('Shopify: nested objects, sub-resource, id field');
    expect(variant).toHaveTextContent('WooCommerce: not documented');
    expect(variant).toHaveTextContent(
      'Variant inside Product (1:n); Variant refers to Product (n:1)',
    );
    // the evidence is quoted, per API, as plain text
    await userEvent.click(within(variant).getByText(/Evidence in the docs/));
    expect(within(variant).getByText('The variants of the product.')).toBeInTheDocument();
    expect(
      within(variant).getByText('GET /admin/api/{version}/products/{product_id}/variants.json'),
    ).toBeInTheDocument();
  });

  it('says so when the docs connect nothing to the concept', async () => {
    renderApp('/models/related?apis=shopify,woocommerce&concept=Warehouse');
    expect(await screen.findByText('No related concepts found for Warehouse')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Create a model set' })).toBeInTheDocument();
    expect(within(bar()).getByRole('button', { name: 'Create with Claude' })).toBeDisabled();
  });

  it('needs two APIs and a concept', async () => {
    renderApp('/models/related?apis=shopify&concept=Product');
    expect(await screen.findByText('Pick a concept first')).toBeInTheDocument();
  });

  it('shows an error with a retry when the server fails', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/suggest-related`, () =>
        HttpResponse.json({ error: 'internal', message: 'boom' }, { status: 500 }),
      ),
    );
    renderApp(url);
    expect(await screen.findByText('Could not find related concepts')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });

  it('offers the alias, with the evidence of both APIs, and the person decides', async () => {
    renderApp(url);
    const alias = await screen.findByRole('region', { name: 'Same thing, different names?' });
    expect(alias).toHaveTextContent('Variant (Shopify) and Variation (WooCommerce)');
    expect(alias).toHaveTextContent('The docs do not say they are the same thing');
    expect(alias).toHaveTextContent('/products/{product_id}/variants');
    expect(alias).toHaveTextContent('/products/{product_id}/variations');
    // not accepted by default: both stay separate concepts
    expect(within(alias).getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Variation' })).toBeEnabled();
  });

  it('accepting the alias makes the two names one concept, called after the first API', async () => {
    renderApp(url);
    await screen.findByRole('region', { name: 'Same thing, different names?' });
    await userEvent.click(screen.getByRole('checkbox', { name: 'Variant' }));
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Treat Variant and Variation as one concept' }),
    );
    // the pick stays, under the common name; the second name points at it
    expect(screen.getByRole('checkbox', { name: 'Variant' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Variation' })).toBeChecked();
    expect(row('Variation')).toHaveTextContent('Same concept as Variant');
    expect(bar()).toHaveTextContent('2 models: Product, Variant');
    expect(bar()).toHaveTextContent('Variant: Variant = Variation (accepted as one concept)');
    // un-picking through the second name un-picks the one concept
    await userEvent.click(screen.getByRole('checkbox', { name: 'Variation' }));
    expect(screen.getByRole('checkbox', { name: 'Variant' })).not.toBeChecked();
    expect(bar()).toHaveTextContent('Product alone is not a set');
  });
});

describe('Create a set with Claude', () => {
  it('needs a related concept first, then opens a session with the prompt', async () => {
    renderApp(url);
    await loaded();
    const create = within(bar()).getByRole('button', { name: 'Create with Claude' });
    expect(create).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Image' }));
    expect(bar()).toHaveTextContent('2 models: Product, Image');
    await userEvent.click(create);
    const panel = await screen.findByRole('region', { name: 'Create the set with Claude' });
    expect(within(panel).getByLabelText('Prompt for Claude')).toHaveTextContent(
      /get_set_context\("ss-mock\d+"\).*Product, Image.*submit_model_set/,
    );
    expect(within(panel).getByText('Waiting for Claude')).toBeInTheDocument();
  });

  it('sends the concepts and the accepted alias (and only it) to the server', async () => {
    let body: unknown;
    server.use(
      http.post(`${TEST_API_BASE}/v1/model-sets/sessions`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          setSessionId: 'ss-1',
          inputs: [],
          memberSessions: {},
          contextUrl: '/x',
          claudePrompt: 'prompt',
        });
      }),
    );
    renderApp(url);
    await loaded();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Variant' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Image' }));
    await userEvent.click(within(bar()).getByRole('button', { name: 'Create with Claude' }));
    await screen.findByRole('region', { name: 'Create the set with Claude' });
    // not accepted: no aliases key at all
    expect(body).toEqual({
      apis: ['shopify', 'woocommerce'],
      concepts: ['Product', 'Variant', 'Image'],
    });
  });

  it('with the alias accepted, the request carries it under the name each API uses', async () => {
    let body: unknown;
    server.use(
      http.post(`${TEST_API_BASE}/v1/model-sets/sessions`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          setSessionId: 'ss-1',
          inputs: [],
          memberSessions: {},
          contextUrl: '/x',
          claudePrompt: 'prompt',
        });
      }),
    );
    renderApp(url);
    await screen.findByRole('region', { name: 'Same thing, different names?' });
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Treat Variant and Variation as one concept' }),
    );
    await userEvent.click(screen.getByRole('checkbox', { name: 'Variant' }));
    await userEvent.click(within(bar()).getByRole('button', { name: 'Create with Claude' }));
    await screen.findByRole('region', { name: 'Create the set with Claude' });
    expect(body).toEqual({
      apis: ['shopify', 'woocommerce'],
      concepts: ['Product', 'Variant'],
      aliases: [{ concept: 'Variant', names: { shopify: 'Variant', woocommerce: 'Variation' } }],
    });
  });

  it('opens the set when Claude has stored it (the poll sees snake_case set_id)', async () => {
    const { router } = renderApp(url);
    await loaded();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Image' }));
    await userEvent.click(within(bar()).getByRole('button', { name: 'Create with Claude' }));
    const panel = await screen.findByRole('region', { name: 'Create the set with Claude' });
    const id = /get_set_context\("(ss-mock\d+)"\)/.exec(
      within(panel).getByLabelText('Prompt for Claude').textContent ?? '',
    )?.[1];
    // Claude submits through the connector (here: the mock's stand-in for it)
    await fetch(`${TEST_API_BASE}/v1/model-sets/sessions/${id}/draft`, {
      method: 'POST',
      body: '{}',
    });
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/model-sets\/u-set-mock/),
    );
  });

  it('can be cancelled, and shows when the session could not start', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/model-sets/sessions`, () =>
        HttpResponse.json({ error: 'rate_limited', message: 'slow down' }, { status: 429 }),
      ),
    );
    renderApp(url);
    await loaded();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Image' }));
    await userEvent.click(within(bar()).getByRole('button', { name: 'Create with Claude' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests right now');
    expect(
      screen.queryByRole('region', { name: 'Create the set with Claude' }),
    ).not.toBeInTheDocument();
  });

  it('a set holds at most eight models: the ninth is not offered', async () => {
    const related = Array.from({ length: 8 }, (_, i) => ({
      id: `c${i}`,
      name: `Concept${i}`,
      kinds: { shopify: ['nested'] },
      candidates: [],
    }));
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/suggest-related`, () =>
        HttpResponse.json({
          apis: [],
          concept: { id: 'product', name: 'Product' },
          related,
          total: 8,
          limit: 24,
          offset: 0,
          nextOffset: null,
          aliases: [],
        }),
      ),
    );
    renderApp(url);
    await loaded();
    for (let i = 0; i < 7; i += 1)
      await userEvent.click(screen.getByRole('checkbox', { name: `Concept${i}` }));
    expect(bar()).toHaveTextContent('8 models');
    expect(bar()).toHaveTextContent('the most a set can have is 8');
    expect(screen.getByRole('checkbox', { name: 'Concept7' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Concept0' })).toBeEnabled(); // still possible to remove one
  });
});

describe('Paste a draft yourself (set session)', () => {
  async function panel(signedIn = false) {
    if (signedIn) authStore.signIn('pl_ok', 'maintainer', false);
    const view = renderApp(url);
    await loaded();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Image' }));
    await userEvent.click(within(bar()).getByRole('button', { name: 'Create with Claude' }));
    const p = await screen.findByRole('region', { name: 'Create the set with Claude' });
    return { p, ...view };
  }
  const paste = async (p: HTMLElement, text: string) => {
    const box = within(p).getByLabelText('Draft JSON');
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste(text);
  };
  const submit = (p: HTMLElement) =>
    userEvent.click(within(p).getByRole('button', { name: 'Submit draft' }));

  it('offers the set and every member model as what the draft is, and says where it is stored', async () => {
    const { p } = await panel();
    const kind = within(p).getByLabelText('This draft is');
    expect(
      within(kind)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['the set', 'the Product model', 'the Image model']);
    expect(within(p).getByRole('button', { name: 'Submit draft' })).toBeDisabled();
    expect(within(p).getByText('Stored unlisted: only people with the link.')).toBeInTheDocument();
  });

  it('says a signed-in maintainer gets an unreleased set', async () => {
    const { p } = await panel(true);
    expect(within(p).getByText('Stored unreleased.')).toBeInTheDocument();
  });

  it('rejects text that is not JSON before calling the server', async () => {
    const { p } = await panel();
    await paste(p, '{ nope');
    await submit(p);
    expect(await within(p).findByRole('alert')).toHaveTextContent('That is not valid JSON');
  });

  it('shows the issues of a refused set draft and stays on the page', async () => {
    const { p, router } = await panel();
    await paste(p, '{"refuse":"relation"}');
    await submit(p);
    const alert = await within(p).findByRole('alert');
    expect(alert).toHaveTextContent('The draft was refused, nothing was stored');
    expect(alert).toHaveTextContent('RELATION_INVALID');
    expect(alert).toHaveTextContent('Order has no field "items" that can hold Product');
    expect(router.state.location.pathname).toBe('/models/related');
  });

  it("stores a member's model first, lists it, and goes back to the set", async () => {
    const { p } = await panel();
    await userEvent.selectOptions(within(p).getByLabelText('This draft is'), 'Image');
    await paste(p, '{"name":"Image","fields":[{"name":"url"}]}');
    await submit(p);
    const stored = await within(p).findByRole('list', { name: 'Stored member models' });
    expect(stored).toHaveTextContent(/Image:\s*stored\s*u-mock/);
    expect(within(p).getByLabelText('Draft JSON')).toHaveValue('');
    expect(within(p).getByLabelText('This draft is')).toHaveValue('set');
    expect(localStorage.getItem('plume-collection')).toMatch(/^c-MockCollection\d+$/); // the first save started the link
  });

  it('a refused member draft shows its issues, and nothing is listed as stored', async () => {
    const { p } = await panel();
    await userEvent.selectOptions(within(p).getByLabelText('This draft is'), 'Product');
    await paste(p, '{"name":"Product","fields":[{"name":"id"}],"refuse":"quote"}');
    await submit(p);
    expect(await within(p).findByRole('alert')).toHaveTextContent('QUOTE_NOT_FOUND');
    expect(within(p).queryByRole('list', { name: 'Stored member models' })).not.toBeInTheDocument();
  });

  it('opens the set once stored, keeps the My models link and shows it once', async () => {
    const { p, router } = await panel();
    await paste(
      p,
      '{"name":"Product + Image","members":{"Product":"u-1","Image":"u-2"},"relations":[]}',
    );
    await submit(p);
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/^\/model-sets\/u-set-mock/),
    );
    // the member model and the set joined the same link
    expect(localStorage.getItem('plume-collection')).toMatch(/^c-MockCollection\d+$/);
    expect(await screen.findByText('Your model set is saved, and unlisted')).toBeInTheDocument();
  });
});

describe('Generate the set on the server (maintainer)', () => {
  async function start(concept = 'Product', pick = 'Image') {
    authStore.signIn('pl_ok', 'maintainer', true);
    const view = renderApp(`/models/related?apis=shopify,woocommerce&concept=${concept}`);
    await loaded();
    await userEvent.click(screen.getByRole('checkbox', { name: pick }));
    return view;
  }

  it('offers the server first and Claude as the alternative', async () => {
    await start();
    expect(within(bar()).getByRole('button', { name: 'Generate the set' })).toBeEnabled();
    expect(within(bar()).getByRole('button', { name: 'Use Claude instead' })).toBeInTheDocument();
  });

  it('follows the job: every model, then the proposals, then opens the unreleased set', async () => {
    const { router } = await start();
    await userEvent.click(within(bar()).getByRole('button', { name: 'Generate the set' }));
    const panel = await screen.findByRole('region', {
      name: 'Generation of the set on the server',
    });
    expect(panel).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/model-sets\/set_job/));
  });

  it('shows the server failure and offers Claude instead', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/model-sets/generate`, () =>
        HttpResponse.json({ jobId: 'mj-fail', status: 'queued', eventsUrl: '/x' }, { status: 202 }),
      ),
      http.get(`${TEST_API_BASE}/v1/models/jobs/mj-fail/events`, () => {
        const enc = new TextEncoder();
        const sse = (id: number, event: string, data: object) =>
          enc.encode(`id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
        return new HttpResponse(
          new ReadableStream({
            start(c) {
              c.enqueue(
                sse(1, 'started', { apis: ['shopify', 'woocommerce'], concept: 'Product+Image' }),
              );
              c.enqueue(sse(2, 'member', { concept: 'Product', snapshotId: 'm-1', round: 1 }));
              c.enqueue(
                sse(3, 'failed', { code: 'draft_refused', message: 'no valid Image model' }),
              );
              c.enqueue(sse(4, 'done', { status: 'failed', snapshotId: null, setId: null }));
              c.close();
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        );
      }),
    );
    await start();
    await userEvent.click(within(bar()).getByRole('button', { name: 'Generate the set' }));
    const panel = await screen.findByRole('region', {
      name: 'Generation of the set on the server',
    });
    expect(await within(panel).findByText(/no valid Image model/)).toBeInTheDocument();
    expect(within(panel).getByText('Product:', { exact: false })).toBeInTheDocument();
    expect(within(panel).getByText('model written')).toBeInTheDocument();
    expect(within(panel).getByText('Image: waiting')).toBeInTheDocument();
    expect(within(panel).getByText(/Nothing was stored/)).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole('button', { name: 'Use Claude instead' }));
    expect(
      await screen.findByRole('region', { name: 'Create the set with Claude' }),
    ).toBeInTheDocument();
  });

  it('no model key on the server (503): says so and offers the Claude flow', async () => {
    await start('Order', 'LineItem');
    // the mock answers 503 when the first concept is "Refund"; here the server is told to refuse
    server.use(
      http.post(`${TEST_API_BASE}/v1/model-sets/generate`, () =>
        HttpResponse.json({ error: 'llm_unavailable', message: 'not configured' }, { status: 503 }),
      ),
    );
    await userEvent.click(within(bar()).getByRole('button', { name: 'Generate the set' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Server-side generation is not configured',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Create with Claude instead' }));
    expect(
      await screen.findByRole('region', { name: 'Create the set with Claude' }),
    ).toBeInTheDocument();
  });

  it('with generation known to be off, only the Claude path is offered, and it says why', async () => {
    authStore.signIn('pl_ok', 'maintainer', false);
    renderApp(url);
    await loaded();
    expect(within(bar()).getByRole('button', { name: 'Create with Claude' })).toBeInTheDocument();
    expect(
      within(bar()).queryByRole('button', { name: 'Generate the set' }),
    ).not.toBeInTheDocument();
    expect(bar()).toHaveTextContent('Server-side generation is not configured on this Plume');
  });

  it('without a token the server is never offered', async () => {
    renderApp(url);
    await loaded();
    expect(
      within(bar()).queryByRole('button', { name: 'Generate the set' }),
    ).not.toBeInTheDocument();
  });
});

describe('Where the page is reached from', () => {
  it('every suggestion links to its related concepts, keeping the APIs', async () => {
    renderApp('/models/suggest?apis=shopify,woocommerce,mirakl');
    const link = await screen.findByRole('link', { name: 'Related concepts of Order' });
    expect(link).toHaveAttribute(
      'href',
      '/models/related?apis=shopify,woocommerce,mirakl&concept=Order',
    );
  });
});
