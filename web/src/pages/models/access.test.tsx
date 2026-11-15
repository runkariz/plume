import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { inventorySnapshot } from '@/mocks/modelData';
import { DEMO_OWNER_KEY, UNLISTED_V3, UNRELEASED } from '@/mocks/modelStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { forgetOwnerKeys, readOwnerKeys, saveOwnerKey, shareLink } from '@/lib/ownerKeys';
import { reduce } from './ModelJobProgress';
import { pollConfig } from './GenerateSession';

const suggest = '/models/suggest?apis=shopify,woocommerce,mirakl';

beforeEach(() => {
  pollConfig.ms = 40;
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE)); // a fresh mock backend per test
});
afterEach(() => {
  pollConfig.ms = 3000;
});

describe('Generate on the server (signed-in maintainer)', () => {
  it('writes the model on the server and opens it UNRELEASED for review', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(suggest);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Shipment' }));
    // no Claude session, no prompt: the job writes it
    expect(await screen.findByRole('heading', { level: 1, name: 'Shipment' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Generation session' })).not.toBeInTheDocument();
    const banner = screen
      .getByText('Unreleased: waiting for your review')
      .closest('div') as HTMLElement;
    expect(
      within(banner.parentElement as HTMLElement).getByRole('button', { name: 'Release' }),
    ).toBeEnabled();
    expect(screen.getByText('Unreleased', { selector: '.chip' })).toBeInTheDocument();
  });

  it('shows every refused round with its issues, then the failure, and offers Claude instead', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(suggest);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Customer' }));
    const panel = await screen.findByRole('region', { name: 'Generation on the server' });
    expect(await within(panel).findByText('Read 12 documents (214 fields)')).toBeInTheDocument();
    const failure = await within(panel).findByText(/No accepted draft after 3 rounds/);
    expect(failure.closest('[role], div')).toBeInTheDocument();
    expect(within(panel).getByText(/Round 3 of 3/)).toBeInTheDocument();
    expect(within(panel).getAllByText('refused, 1 issue')).toHaveLength(3);
    expect(within(panel).getAllByText('QUOTE_NOT_FOUND')).toHaveLength(3);
    expect(within(panel).getByText(/Nothing was stored/)).toBeInTheDocument();
    // the Claude flow for the same concept
    await userEvent.click(within(panel).getByRole('button', { name: 'Use Claude instead' }));
    expect(await screen.findByRole('region', { name: 'Generation session' })).toBeInTheDocument();
  });

  it('says so when the server has no model key (503) and offers the Claude flow', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(suggest);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Location' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Server-side generation is not configured on this Plume');
    await userEvent.click(within(alert).getByRole('button', { name: 'Use Claude instead' }));
    expect(await screen.findByRole('region', { name: 'Generation session' })).toBeInTheDocument();
  });

  it('a signed-out visitor never gets a server job: the Claude session, stored unlisted', async () => {
    renderApp(suggest);
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Shipment' }));
    expect(await screen.findByRole('region', { name: 'Generation session' })).toBeInTheDocument();
    expect(
      screen.queryByRole('region', { name: 'Generation on the server' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /with Claude instead/ })).not.toBeInTheDocument();
  });

  it('reduces the events: refused rounds keep their issues, accepted names the model', () => {
    const empty = {
      documents: null,
      fields: null,
      rounds: [],
      maxRounds: 3,
      snapshotId: null,
      failure: null,
      finished: false,
    };
    const issue = { code: 'X', field: 'f', api: null, message: 'm' };
    let p = reduce(empty, { type: 'round', n: 1, of: 3 });
    p = reduce(p, { type: 'round', n: 1, of: 3 }); // a replay after a reconnect changes nothing
    p = reduce(p, { type: 'refused', round: 1, issues: [issue] });
    p = reduce(p, { type: 'round', n: 2, of: 3 });
    p = reduce(p, { type: 'accepted', snapshotId: 'm-1' });
    p = reduce(p, { type: 'done', status: 'succeeded', snapshotId: 'm-1' });
    expect(p.rounds).toEqual([
      { n: 1, issues: [issue] },
      { n: 2, issues: null },
    ]);
    expect(p.snapshotId).toBe('m-1');
    expect(p.finished).toBe(true);
    expect(reduce(p, { type: 'failed', code: 'x', message: 'boom' }).failure).toBe('boom');
  });
});

describe('Review: release or discard an unreleased model', () => {
  const open = async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(`/models/${UNRELEASED}`);
    return screen.findByRole('button', { name: 'Release' });
  };

  it('Release makes it Official and the review banner goes away', async () => {
    await userEvent.click(await open());
    expect(await screen.findByText('Official', { selector: '.chip' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Release' })).not.toBeInTheDocument();
    expect(screen.queryByText('Unreleased: waiting for your review')).not.toBeInTheDocument();
  });

  it('Discard asks to confirm, and can be taken back', async () => {
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByText('Discard this model? It cannot be undone.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(screen.queryByText(/cannot be undone/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    await userEvent.click(screen.getByRole('button', { name: 'Yes, discard' }));
    expect(await screen.findByText('Discarded')).toBeInTheDocument();
  });

  it('explains a 409 (someone else decided first) and a rejected token', async () => {
    await open();
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/:id/release`, () =>
        HttpResponse.json({ error: 'invalid_state', message: 'x' }, { status: 409 }),
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Release' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not waiting for review any more');
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/:id/release`, () =>
        HttpResponse.json({ error: 'unauthorized', message: 'x' }, { status: 401 }),
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Release' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Sign in again'));
  });

  it('is invisible to the public: an unreleased model is "not found" without the token', async () => {
    renderApp(`/models/${UNRELEASED}`);
    expect(await screen.findByText('Model not found')).toBeInTheDocument();
  });
});

describe('Lists: who sees which model', () => {
  it('the public list shows Official models only, each with the badge', async () => {
    renderApp('/models');
    const list = await screen.findByRole('region', { name: 'Official models' });
    const names = within(list)
      .getAllByRole('link')
      .map((a) => a.textContent);
    expect(names).toEqual(expect.arrayContaining(['Inventory', 'Order', 'Product']));
    expect(within(list).getAllByText('Official')).toHaveLength(names.length);
    expect(within(list).queryByText('Return')).not.toBeInTheDocument(); // unreleased
    expect(within(list).queryByText(/returns count/)).not.toBeInTheDocument(); // unlisted
    expect(screen.queryByRole('region', { name: 'Waiting for review' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your models' })).not.toBeInTheDocument();
  });

  it('a signed-in maintainer also sees what waits for review', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/models');
    const waiting = await screen.findByRole('region', { name: 'Waiting for review' });
    expect(within(waiting).getByRole('link', { name: 'Return' })).toHaveAttribute(
      'href',
      `/models/${UNRELEASED}`,
    );
    expect(within(waiting).getByText('Unreleased')).toBeInTheDocument();
    // the public list is still official only
    const list = screen.getByRole('region', { name: 'Official models' });
    expect(within(list).queryByText('Return')).not.toBeInTheDocument();
  });

  it('"Your models" lists the models of the owner keys this browser holds, latest version of each', async () => {
    saveOwnerKey(DEMO_OWNER_KEY);
    renderApp('/models');
    const mine = await screen.findByRole('region', { name: 'Your models' });
    expect(within(mine).getAllByRole('link')).toHaveLength(1);
    const row = within(mine)
      .getByRole('link', { name: 'Inventory, with a returns count' })
      .closest('li') as HTMLElement;
    expect(within(row).getByText('v3 of 3')).toBeInTheDocument();
    expect(within(row).getByText('Unlisted')).toBeInTheDocument();
    // the server was asked with POST, so the key is in no URL
    expect(readOwnerKeys()).toEqual([DEMO_OWNER_KEY]);
  });

  it('an unknown owner key shows nothing', async () => {
    saveOwnerKey('ok-someone-else');
    renderApp('/models');
    await screen.findByRole('region', { name: 'Official models' });
    expect(screen.queryByRole('region', { name: 'Your models' })).not.toBeInTheDocument();
  });
});

describe('The model page: lineage, sharing, modifying', () => {
  it('an unlisted model shows its version, where it was based, the versions and the share link', async () => {
    renderApp(`/models/${UNLISTED_V3}`);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Inventory, with a returns count' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Unlisted: anyone with the link')).toBeInTheDocument();
    expect(screen.getByText('v3 of 3')).toBeInTheDocument();
    expect(screen.getByText(/based on/)).toBeInTheDocument();
    // the model it was based on is linked from the line under the title (and listed in the versions)
    const basedOn = screen.getAllByRole('link', { name: 'u-2b8c6e04d15c59e3c9a7f1b40d2e8a63' });
    expect(basedOn[0]).toHaveAttribute('href', '/models/u-2b8c6e04d15c59e3c9a7f1b40d2e8a63');
    await userEvent.click(screen.getByText('Versions of this model (3)'));
    expect(screen.getByText('this version')).toBeInTheDocument();
    const share = screen.getByRole('region', { name: 'Share this model' });
    expect((within(share).getByLabelText('Link to this model') as HTMLInputElement).value).toBe(
      `${window.location.origin}/models/${UNLISTED_V3}`,
    );
    expect(within(share).getByText(/Anyone with this link can open the model/)).toBeInTheDocument();
    // the latest version: no "newer version" notice
    expect(screen.queryByText('A newer version of this model exists')).not.toBeInTheDocument();
  });

  it('an older version points to the latest one', async () => {
    renderApp('/models/u-1a7e5d93c04b48d2b8f6e0a39c1d7f52');
    expect(await screen.findByText('A newer version of this model exists')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the latest version' })).toHaveAttribute(
      'href',
      `/models/${UNLISTED_V3}`,
    );
    expect(screen.getByText('v1 of 3')).toBeInTheDocument();
  });

  it('copies the share link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderApp(`/models/${UNLISTED_V3}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Copy link' }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/models/${UNLISTED_V3}`),
    );
    expect(await screen.findByText('Link copied')).toBeInTheDocument();
  });

  it('"Modify with Claude" gives the prompt the server built, to copy', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderApp(`/models/${UNLISTED_V3}`);
    const card = await screen.findByRole('region', { name: 'Modify with Claude' });
    expect(within(card).getByLabelText('Prompt for Claude')).toHaveTextContent(
      `revise_model with id "${UNLISTED_V3}"`,
    );
    await userEvent.click(within(card).getByRole('button', { name: 'Copy prompt' }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('revise_model')),
    );
    expect(
      await within(card).findByText('Prompt copied: paste it into Claude'),
    ).toBeInTheDocument();
  });

  it('an official model is Official, has no share card, and can still be modified', async () => {
    renderApp('/models/snap_8f3a21');
    await screen.findByRole('heading', { level: 1, name: 'Inventory' });
    expect(screen.getByText('Official')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Share this model' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Modify with Claude' })).toBeInTheDocument();
    expect(screen.queryByText(/of \d+$/, { selector: '.lineage b' })).not.toBeInTheDocument(); // v1 of 1: not mentioned
  });

  it('an older server without visibility fields still shows the model, with nothing invented', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, () => HttpResponse.json(inventorySnapshot)),
    );
    renderApp('/models/snap_8f3a21');
    await screen.findByRole('heading', { level: 1, name: 'Inventory' });
    expect(screen.getByText('Generated, unverified')).toBeInTheDocument();
    expect(screen.queryByText('Official')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Modify with Claude' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Share this model' })).not.toBeInTheDocument();
  });
});

describe('Owner keys in this browser', () => {
  it('stores each key once and can forget them', () => {
    saveOwnerKey('a');
    saveOwnerKey('a');
    saveOwnerKey('b');
    saveOwnerKey('');
    expect(readOwnerKeys()).toEqual(['a', 'b']);
    forgetOwnerKeys();
    expect(readOwnerKeys()).toEqual([]);
  });

  it('survives unavailable or corrupt storage', () => {
    localStorage.setItem('plume-owner-keys', '{not json');
    expect(readOwnerKeys()).toEqual([]);
    localStorage.setItem('plume-owner-keys', '{"a":1}');
    expect(readOwnerKeys()).toEqual([]);
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readOwnerKeys()).toEqual([]);
    expect(() => saveOwnerKey('x')).not.toThrow();
    spy.mockRestore();
  });

  it('builds the share link from this site, not from the server (which may not know its URL)', () => {
    expect(shareLink({ id: 'u-1', sharePath: '/models/u-1' })).toBe(
      `${window.location.origin}/models/u-1`,
    );
    expect(shareLink({ id: 'u-2' })).toBe(`${window.location.origin}/models/u-2`);
  });
});
