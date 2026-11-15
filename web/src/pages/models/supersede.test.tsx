import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { order40Snapshot } from '@/mocks/modelData';
import { OFFICIAL_ORDER_SW, UNRELEASED, UNRELEASED_ORDER } from '@/mocks/modelStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

const OLDER = 'm-order0lder0a1b2c3d4e5f60718293a4b5c';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_ok', 'maintainer');
});
afterEach(() => authStore.signOut());

const choice = () =>
  screen.findByRole('group', { name: /Does this model replace an official one\?/ });
const row = (g: HTMLElement, id: string) =>
  within(g)
    .getByRole('checkbox', { name: new RegExp(id) })
    .closest('li') as HTMLElement;

describe('Release asks which official models of the same concept it replaces', () => {
  it('lists them (any API set) with what covers what and what is stale, and ticks none', async () => {
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    const g = await choice();
    const boxes = within(g).getAllByRole('checkbox');
    expect(boxes).toHaveLength(3);
    expect(boxes.every((b) => !(b as HTMLInputElement).checked)).toBe(true);
    // the Order over Shopify + WooCommerce: its APIs are inside this model's, built on older docs
    const sw = row(g, OFFICIAL_ORDER_SW);
    expect(sw).toHaveTextContent('Shopify, WooCommerce');
    expect(within(sw).getByText('stale')).toBeInTheDocument();
    expect(within(sw).getByText('covered by this model')).toBeInTheDocument();
    // the Orders over three APIs cover Mirakl too: not covered
    expect(within(row(g, OLDER)).getByText('not covered: Mirakl')).toBeInTheDocument();
    expect(within(row(g, order40Snapshot.id)).getByText('not covered: Mirakl')).toBeInTheDocument();
    // nothing has been released yet
    expect(within(g).getByRole('button', { name: 'Release without replacing any' })).toBeEnabled();
    expect(screen.getByText('Unreleased: waiting for your review')).toBeInTheDocument();
  });

  it('can be cancelled: nothing is released', async () => {
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    await userEvent.click(within(await choice()).getByRole('button', { name: 'Cancel' }));
    expect(
      screen.queryByRole('group', { name: /replace an official one/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Release' })).toBeEnabled();
    expect(screen.getByText('Unreleased: waiting for your review')).toBeInTheDocument();
  });

  it('releases without replacing any when none is ticked: the others stay official', async () => {
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    await userEvent.click(
      within(await choice()).getByRole('button', { name: 'Release without replacing any' }),
    );
    expect(await screen.findByText('Official', { selector: '.chip' })).toBeInTheDocument();
    expect(screen.queryByText(/Replaced these official models/)).not.toBeInTheDocument();
    const list = (await fetch(`${TEST_API_BASE}/v1/models`).then((r) => r.json())) as {
      items: { id: string }[];
    };
    expect(list.items.map((i) => i.id)).toContain(order40Snapshot.id);
  });

  it('ticking one that covers an API this model lacks says so; releasing replaces it', async () => {
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    const g = await choice();
    await userEvent.click(within(row(g, order40Snapshot.id)).getByRole('checkbox'));
    expect(within(g).getByRole('status')).toHaveTextContent(
      /covers Mirakl takes that API out of the official lists/,
    );
    await userEvent.click(within(row(g, OFFICIAL_ORDER_SW)).getByRole('checkbox'));
    await userEvent.click(within(g).getByRole('button', { name: 'Release and replace 2' }));
    expect(await screen.findByText('Official', { selector: '.chip' })).toBeInTheDocument();
    const replaced = await screen.findByText(/Replaced these official models when it was released/);
    expect(replaced).toHaveTextContent(order40Snapshot.id);
    expect(replaced).toHaveTextContent(OFFICIAL_ORDER_SW);
    // they leave the official lists but stay readable by id
    const list = (await fetch(`${TEST_API_BASE}/v1/models`).then((r) => r.json())) as {
      items: { id: string }[];
    };
    const ids = list.items.map((i) => i.id);
    expect(ids).not.toContain(order40Snapshot.id);
    expect(ids).not.toContain(OFFICIAL_ORDER_SW);
    expect(ids).toContain(UNRELEASED_ORDER);
  });

  it('a superseded model says by which, is marked, and is readable without a token', async () => {
    await fetch(`${TEST_API_BASE}/v1/models/${UNRELEASED_ORDER}/release`, {
      method: 'POST',
      headers: { Authorization: 'Bearer pl_ok', 'Content-Type': 'application/json' },
      body: JSON.stringify({ supersedes: [OFFICIAL_ORDER_SW] }),
    });
    authStore.signOut();
    renderApp(`/models/${OFFICIAL_ORDER_SW}`);
    const banner = await screen.findByText(`Superseded by ${UNRELEASED_ORDER}`);
    expect(banner).toBeInTheDocument();
    expect(screen.getByRole('link', { name: `open ${UNRELEASED_ORDER}` })).toHaveAttribute(
      'href',
      `/models/${UNRELEASED_ORDER}`,
    );
    expect(screen.getByText('Superseded', { selector: '.chip' })).toBeInTheDocument();
  });

  it('a model with no official model of its concept is released at once, as before', async () => {
    renderApp(`/models/${UNRELEASED}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    expect(await screen.findByText('Official', { selector: '.chip' })).toBeInTheDocument();
    expect(
      screen.queryByRole('group', { name: /replace an official one/ }),
    ).not.toBeInTheDocument();
  });

  it('an older server without /supersedable (404) releases at once too', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id/supersedable`, () =>
        HttpResponse.json({ error: 'not_found', message: 'nope' }, { status: 404 }),
      ),
    );
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    expect(await screen.findByText('Official', { selector: '.chip' })).toBeInTheDocument();
  });

  it('a refused replacement (409) says nothing was released and keeps the dialog', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/:id/release`, () =>
        HttpResponse.json({ error: 'invalid_state', message: 'not a candidate' }, { status: 409 }),
      ),
    );
    renderApp(`/models/${UNRELEASED_ORDER}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    const g = await choice();
    await userEvent.click(within(row(g, OFFICIAL_ORDER_SW)).getByRole('checkbox'));
    await userEvent.click(within(g).getByRole('button', { name: 'Release and replace 1' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Nothing was released: one of the models to replace is no longer an official model of this concept \(not a candidate\)/,
    );
    expect(screen.getByRole('group', { name: /replace an official one/ })).toBeInTheDocument();
    expect(screen.getByText('Unreleased: waiting for your review')).toBeInTheDocument();
  });
});

describe('Retire older models from an official model', () => {
  const panel = () => screen.findByRole('region', { name: 'Retire older models' });

  it('shows the same choice, needs at least one tick, and retires them', async () => {
    renderApp(`/models/${OFFICIAL_ORDER_SW}`);
    const p = await panel();
    await userEvent.click(
      within(p).getByRole('button', { name: 'Retire older models of this concept' }),
    );
    const g = await within(p).findByRole('group', { name: /Retire older models of this concept/ });
    expect(within(g).getAllByRole('checkbox')).toHaveLength(2); // the two Orders over three APIs
    expect(within(g).getByRole('button', { name: 'Retire' })).toBeDisabled();
    await userEvent.click(within(row(g, OLDER)).getByRole('checkbox'));
    await userEvent.click(within(g).getByRole('button', { name: 'Retire 1' }));
    expect(
      await screen.findByText(/Replaced these official models when it was released/),
    ).toHaveTextContent(OLDER);
    // the retired one: superseded by this model
    const old = (await fetch(`${TEST_API_BASE}/v1/models/${OLDER}`).then((r) => r.json())) as {
      visibility: string;
      supersededBy: string;
    };
    expect(old).toMatchObject({ visibility: 'superseded', supersededBy: OFFICIAL_ORDER_SW });
  });

  it('says so when there is no other official model of the concept', async () => {
    renderApp('/models/' + UNRELEASED);
    // an unreleased model has no panel; release it, then ask
    await userEvent.click(await screen.findByRole('button', { name: 'Release' }));
    await screen.findByText('Official', { selector: '.chip' });
    const p = await panel();
    await userEvent.click(
      within(p).getByRole('button', { name: 'Retire older models of this concept' }),
    );
    expect(await within(p).findByRole('status')).toHaveTextContent(
      'There is no other official model of this concept',
    );
  });

  it('is only for a signed-in maintainer on an official model', async () => {
    authStore.signOut();
    renderApp(`/models/${OFFICIAL_ORDER_SW}`);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: 'Retire older models' })).not.toBeInTheDocument();
  });

  it('a refused retirement (409) says nothing was retired', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/:id/supersede`, () =>
        HttpResponse.json({ error: 'invalid_state', message: 'gone' }, { status: 409 }),
      ),
    );
    renderApp(`/models/${OFFICIAL_ORDER_SW}`);
    const p = await panel();
    await userEvent.click(
      within(p).getByRole('button', { name: 'Retire older models of this concept' }),
    );
    const g = await within(p).findByRole('group', { name: /Retire older models/ });
    await userEvent.click(within(row(g, OLDER)).getByRole('checkbox'));
    await userEvent.click(within(g).getByRole('button', { name: 'Retire 1' }));
    await waitFor(() =>
      expect(within(p).getByRole('alert')).toHaveTextContent(/Nothing was retired/),
    );
  });
});
