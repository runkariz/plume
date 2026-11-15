import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { readCollectionId, saveCollectionId } from '@/lib/collection';
import { readOwnerKeys } from '@/lib/ownerKeys';
import { DEMO_COLLECTION, SET_COLLECTION } from '@/mocks/collectionStore';
import { createHandlers } from '@/mocks/handlers';
import { DEMO_OWNER_KEY } from '@/mocks/modelStore';
import { SET_OWNER_KEY } from '@/mocks/setStore';
import { renderApp, testClient } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
});

const get = (id: string) =>
  fetch(`${TEST_API_BASE}/v1/collections/${id}`).then(
    (r) =>
      r.json() as Promise<{
        mergedInto: string | null;
        count: number;
        models: { name: string }[];
        sets: { name: string }[];
      }>,
  );

describe('"Your models" on /models: the link this browser holds', () => {
  it('lists models AND sets of the link, with the link to copy and a way to the page', async () => {
    await testClient().mergeCollection(DEMO_COLLECTION, [SET_COLLECTION]); // one link holding both
    saveCollectionId(DEMO_COLLECTION);
    renderApp('/models');
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(
      await within(mine).findByRole('link', { name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
    expect(within(mine).getByRole('link', { name: 'Open the My models page' })).toHaveAttribute(
      'href',
      `/mine/${DEMO_COLLECTION}`,
    );
    const sets = await screen.findByRole('region', { name: 'Your model sets' });
    expect(within(sets).getByRole('link', { name: 'Shop (my version)' })).toBeInTheDocument();
  });

  it('says "Nothing saved yet" for a link without items, still showing the link', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/collections/:id`, ({ params }) =>
        HttpResponse.json({
          id: params.id,
          url: `/mine/${String(params.id)}`,
          mergedInto: null,
          count: 0,
          models: [],
          sets: [],
        }),
      ),
    );
    saveCollectionId(DEMO_COLLECTION);
    renderApp('/models');
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(await within(mine).findByText('Nothing saved yet.')).toBeInTheDocument();
    expect(within(mine).getByLabelText('Link to My models')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your model sets' })).not.toBeInTheDocument();
  });

  it('follows a link that was merged into another (and keeps that one)', async () => {
    await testClient().mergeCollection(SET_COLLECTION, [DEMO_COLLECTION]);
    saveCollectionId(DEMO_COLLECTION);
    renderApp('/models');
    await waitFor(() => expect(readCollectionId()).toBe(SET_COLLECTION));
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(
      await within(mine).findByRole('link', { name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
  });

  it('a failed load says so and offers to try again (nothing is forgotten)', async () => {
    saveCollectionId(DEMO_COLLECTION);
    server.use(http.get(`${TEST_API_BASE}/v1/collections/:id`, () => HttpResponse.error()));
    renderApp('/models');
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(await within(mine).findByRole('alert')).toHaveTextContent('Could not load your models');
    expect(within(mine).getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(readCollectionId()).toBe(DEMO_COLLECTION);
  });
});

describe('old owner keys become the link they turned into, once', () => {
  it('a held key is listed, its link is kept and the key is forgotten', async () => {
    localStorage.setItem('plume-owner-keys', JSON.stringify([DEMO_OWNER_KEY]));
    renderApp('/models');
    await waitFor(() => expect(readCollectionId()).toBe(DEMO_COLLECTION));
    expect(readOwnerKeys()).toEqual([]);
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(
      await within(mine).findByRole('link', { name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
  });

  it('several keys keep the first link and merge the others into it', async () => {
    localStorage.setItem('plume-owner-keys', JSON.stringify([DEMO_OWNER_KEY, SET_OWNER_KEY]));
    renderApp('/models');
    await waitFor(() => expect(readCollectionId()).toBe(DEMO_COLLECTION));
    await waitFor(() => expect(readOwnerKeys()).toEqual([]));
    const merged = await get(DEMO_COLLECTION);
    expect(merged.sets.map((s) => s.name)).toContain('Shop (my version)');
    expect((await get(SET_COLLECTION)).mergedInto).toBe(DEMO_COLLECTION);
    expect(await screen.findByRole('region', { name: 'Your model sets' })).toBeInTheDocument();
  });

  it('with a link already held, the keys are merged into it', async () => {
    saveCollectionId(SET_COLLECTION);
    localStorage.setItem('plume-owner-keys', JSON.stringify([DEMO_OWNER_KEY]));
    renderApp('/models');
    await waitFor(() => expect(readOwnerKeys()).toEqual([]));
    expect(readCollectionId()).toBe(SET_COLLECTION);
    expect((await get(SET_COLLECTION)).models.map((m) => m.name)).toContain(
      'Inventory, with a returns count',
    );
  });

  it('a failure changes nothing: the keys stay for the next visit', async () => {
    localStorage.setItem('plume-owner-keys', JSON.stringify([DEMO_OWNER_KEY]));
    server.use(http.post(`${TEST_API_BASE}/v1/models/mine`, () => HttpResponse.error()));
    renderApp('/models');
    await screen.findByRole('region', { name: 'Official models' });
    await new Promise((r) => setTimeout(r, 100));
    expect(readOwnerKeys()).toEqual([DEMO_OWNER_KEY]);
    expect(readCollectionId()).toBeNull();
  });

  it('keys this Plume does not know are kept, and nothing is invented', async () => {
    localStorage.setItem('plume-owner-keys', JSON.stringify(['ok-someone-else']));
    renderApp('/models');
    await screen.findByRole('region', { name: 'Official models' });
    await new Promise((r) => setTimeout(r, 100));
    expect(readCollectionId()).toBeNull();
    expect(screen.queryByRole('region', { name: 'Your models' })).not.toBeInTheDocument();
  });
});

describe('Open another My models link', () => {
  const open = async () => {
    const view = renderApp('/models');
    const region = await screen.findByRole('region', { name: 'Open a My models link' });
    await userEvent.click(within(region).getByText(/Have a My models link/));
    return { region, ...view };
  };
  const paste = async (region: HTMLElement, text: string) => {
    const box = within(region).getByLabelText('My models link');
    await userEvent.click(box);
    await userEvent.paste(text);
    await userEvent.click(within(region).getByRole('button', { name: 'Open link' }));
  };

  it('takes the whole link or just its id, checks it, keeps it, and lists its models', async () => {
    const { region } = await open();
    await paste(region, `https://plume.example/mine/${DEMO_COLLECTION}`);
    expect(await within(region).findByRole('status')).toHaveTextContent(/Opened: 1 item/);
    expect(readCollectionId()).toBe(DEMO_COLLECTION);
    expect(within(region).getByLabelText('My models link')).toHaveValue('');
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(
      await within(mine).findByRole('link', { name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
  });

  it('says what is wrong with something that is not a link, without calling the server', async () => {
    const calls: string[] = [];
    server.events.on('request:start', ({ request }) => {
      if (request.url.includes('/collections/')) calls.push(request.url);
    });
    const { region } = await open();
    await paste(region, 'ok-an-old-owner-key');
    expect(await within(region).findByRole('alert')).toHaveTextContent(
      'That is not a My models link',
    );
    server.events.removeAllListeners();
    expect(calls).toEqual([]);
    expect(readCollectionId()).toBeNull();
  });

  it('a link this Plume does not know is refused and not kept', async () => {
    const { region } = await open();
    await paste(region, 'c-NobodyHasThisLink012345');
    expect(await within(region).findByRole('alert')).toHaveTextContent('does not know that link');
    expect(readCollectionId()).toBeNull();
  });

  it('a blocked network says so, keeps the panel open with what was typed, and keeps nothing', async () => {
    server.use(http.get(`${TEST_API_BASE}/v1/collections/:id`, () => HttpResponse.error()));
    const { region } = await open();
    await paste(region, DEMO_COLLECTION);
    expect(await within(region).findByRole('alert')).toHaveTextContent(
      'Could not reach the Plume API',
    );
    expect(region.querySelector('details')).toHaveAttribute('open');
    expect(within(region).getByLabelText('My models link')).toHaveValue(DEMO_COLLECTION);
    expect(readCollectionId()).toBeNull();
  });

  it('a link that was merged into another opens the one it moved to', async () => {
    await testClient().mergeCollection(SET_COLLECTION, [DEMO_COLLECTION]);
    const { region } = await open();
    await paste(region, DEMO_COLLECTION);
    expect(await within(region).findByRole('status')).toHaveTextContent('merged into another one');
    expect(readCollectionId()).toBe(SET_COLLECTION);
  });
});

describe('the My models page (/mine/<id>)', () => {
  it('lists what is under the link, as a page anyone with the link can open', async () => {
    renderApp(`/mine/${DEMO_COLLECTION}`);
    expect(await screen.findByRole('heading', { level: 1, name: 'My models' })).toBeInTheDocument();
    const models = await screen.findByRole('region', { name: 'Models' });
    expect(
      within(models).getByRole('link', { name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'Model sets' })).getByText('No model sets yet.'),
    ).toBeInTheDocument();
    expect(screen.getByText('1 item saved under this link')).toBeInTheDocument();
    expect(screen.getByLabelText('Link to My models')).toHaveValue(
      `${window.location.origin}/mine/${DEMO_COLLECTION}`,
    );
  });

  it('opening it does not change this browser; "Use this link in this browser" does', async () => {
    renderApp(`/mine/${DEMO_COLLECTION}`);
    await screen.findByRole('region', { name: 'Models' });
    expect(readCollectionId()).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Use this link in this browser' }));
    expect(readCollectionId()).toBe(DEMO_COLLECTION);
    expect(await screen.findByText(/This browser uses this link now/)).toBeInTheDocument();
  });

  it('knows when it is the link of this browser, and then offers nothing to switch', async () => {
    saveCollectionId(DEMO_COLLECTION);
    renderApp(`/mine/${DEMO_COLLECTION}`);
    expect(await screen.findByText(/the link of this browser/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Use this link in this browser' }),
    ).not.toBeInTheDocument();
  });

  it('merges this browser’s other link into it, then uses it', async () => {
    saveCollectionId(SET_COLLECTION);
    renderApp(`/mine/${DEMO_COLLECTION}`);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Merge my other link into this one' }),
    );
    expect(
      await screen.findByText(/Merged: everything from your other link is here now/),
    ).toBeInTheDocument();
    expect(readCollectionId()).toBe(DEMO_COLLECTION);
    const sets = await screen.findByRole('region', { name: 'Model sets' });
    expect(
      await within(sets).findByRole('link', { name: 'Shop (my version)' }),
    ).toBeInTheDocument();
    expect((await get(SET_COLLECTION)).mergedInto).toBe(DEMO_COLLECTION);
  });

  it('says a merge over the cap moved nothing', async () => {
    saveCollectionId(SET_COLLECTION);
    server.use(
      http.post(`${TEST_API_BASE}/v1/collections/:id/merge`, () =>
        HttpResponse.json({ error: 'invalid_request', message: 'too many' }, { status: 400 }),
      ),
    );
    renderApp(`/mine/${DEMO_COLLECTION}`);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Merge my other link into this one' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'holds at most 500 items: nothing was merged',
    );
    expect(readCollectionId()).toBe(SET_COLLECTION);
  });

  it('a link that was emptied by a merge points to where its models went', async () => {
    await testClient().mergeCollection(SET_COLLECTION, [DEMO_COLLECTION]);
    renderApp(`/mine/${DEMO_COLLECTION}`);
    const banner = await screen.findByText('This link was merged into another one');
    expect(banner).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'open the one they are in now' })).toHaveAttribute(
      'href',
      `/mine/${SET_COLLECTION}`,
    );
    expect(screen.queryByRole('region', { name: 'Models' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Use this link in this browser' }),
    ).not.toBeInTheDocument();
  });

  it('a link this Plume does not know, or that is not a link at all, says so', async () => {
    const { unmount } = renderApp('/mine/c-NobodyHasThisLink012345');
    expect(await screen.findByText('This My models link is not known here')).toBeInTheDocument();
    unmount();
    renderApp('/mine/not-a-link');
    expect(await screen.findByText('This My models link is not known here')).toBeInTheDocument();
  });

  it('an empty link says there are no models and no sets yet', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/collections/:id`, ({ params }) =>
        HttpResponse.json({
          id: params.id,
          url: `/mine/${String(params.id)}`,
          mergedInto: null,
          count: 0,
          models: [],
          sets: [],
        }),
      ),
    );
    renderApp(`/mine/${DEMO_COLLECTION}`);
    expect(await screen.findByText('0 items saved under this link')).toBeInTheDocument();
    expect(screen.getByText('No models yet.')).toBeInTheDocument();
    expect(screen.getByText('No model sets yet.')).toBeInTheDocument();
  });
});

describe('saving joins the link, through the client', () => {
  it('sends ?collection= only when there is one, and the server answers the same link (created false)', async () => {
    const urls: string[] = [];
    server.events.on('request:start', ({ request }) => {
      if (request.url.includes('/draft')) urls.push(request.url);
    });
    const c = testClient();
    const s1 = await c.generateModel({
      apis: ['shopify', 'woocommerce'],
      concept: 'shipment',
      engine: 'claude',
    });
    const first = await c.submitModelDraft((s1 as { sessionId: string }).sessionId, {
      name: 'Shipment',
      fields: [{ name: 'x' }],
    });
    expect(first.collection).toMatchObject({
      created: true,
      url: expect.stringMatching(/^\/mine\/c-/),
    });
    const s2 = await c.generateModel({
      apis: ['shopify', 'woocommerce'],
      concept: 'customer',
      engine: 'claude',
    });
    const second = await c.submitModelDraft(
      (s2 as { sessionId: string }).sessionId,
      { name: 'Customer', fields: [{ name: 'x' }] },
      undefined,
      { collection: first.collection?.id },
    );
    server.events.removeAllListeners();
    expect(new URL(urls[0] ?? '').searchParams.has('collection')).toBe(false);
    expect(new URL(urls[1] ?? '').searchParams.get('collection')).toBe(first.collection?.id);
    expect(second.collection).toMatchObject({ id: first.collection?.id, created: false });
    expect((await get(first.collection?.id ?? '')).models.map((m) => m.name).sort()).toEqual([
      'Customer',
      'Shipment',
    ]);
  });
});
