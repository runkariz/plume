import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { removedSummary } from './RemoveApi';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_ok', 'maintainer');
});
afterEach(() => authStore.signOut());

const open = async (name = 'Stripe API') => {
  renderApp('/maintainer');
  await userEvent.click(await screen.findByRole('button', { name: `Remove ${name}` }));
  return screen.findByRole('group', { name: /^Remove / });
};

const removal = (pinnedBy: unknown[]) =>
  http.get(`${TEST_API_BASE}/v1/apis/stripe/removal`, () =>
    HttpResponse.json({ api: 'stripe', pinnedBy }),
  );

describe('a maintainer removes an API', () => {
  it('needs the id typed, then removes it and says what was deleted', async () => {
    server.use(removal([]));
    const panel = await open();
    const button = within(panel).getByRole('button', { name: 'Remove stripe' });
    expect(button).toBeDisabled();
    await userEvent.type(within(panel).getByLabelText(/Type stripe to confirm/), 'strip');
    expect(button).toBeDisabled();
    await userEvent.type(within(panel).getByLabelText(/Type stripe to confirm/), 'e');
    expect(button).toBeEnabled();
    await userEvent.click(button);
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('Removed stripe');
    expect(notice).toHaveTextContent('Deleted documents 12');
    // gone from the list
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Remove Stripe API' })).not.toBeInTheDocument(),
    );
  });

  it('lists the models and sets that use it and asks for force before it removes', async () => {
    let sent: unknown = null;
    server.use(
      removal([
        { type: 'model', id: 'm1', name: 'Order', visibility: 'official' },
        { type: 'set', id: 's1', name: 'Commerce set', visibility: 'unreleased' },
      ]),
      http.delete(`${TEST_API_BASE}/v1/apis/stripe`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          api: 'stripe',
          removed: { documents: 3, builds: 1, evals: 0, api: 1 },
          retired: [
            { type: 'model', id: 'm1', name: 'Order', visibility: 'official', now: 'superseded' },
            {
              type: 'set',
              id: 's1',
              name: 'Commerce set',
              visibility: 'unreleased',
              now: 'discarded',
            },
          ],
          forced: true,
        });
      }),
    );
    const panel = await open();
    const list = await within(panel).findByRole('list', {
      name: 'Models and sets that use this API',
    });
    expect(list).toHaveTextContent('Order');
    expect(list).toHaveTextContent('Commerce set');
    await userEvent.type(within(panel).getByLabelText(/Type stripe to confirm/), 'stripe');
    // typed, but the models and sets are not agreed to yet
    expect(within(panel).getByRole('button', { name: 'Remove stripe' })).toBeDisabled();
    await userEvent.click(within(panel).getByRole('checkbox'));
    await userEvent.type(within(panel).getByLabelText(/Reason/), ' cleaning up');
    await userEvent.click(within(panel).getByRole('button', { name: 'Remove stripe' }));
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('Order');
    expect(notice).toHaveTextContent('now superseded');
    expect(notice).toHaveTextContent('now discarded');
    expect(sent).toEqual({ confirm: 'stripe', force: true, reason: 'cleaning up' });
  });

  it('shows who pins it when the server says api_in_use after the check', async () => {
    server.use(
      removal([]),
      http.delete(`${TEST_API_BASE}/v1/apis/stripe`, () =>
        HttpResponse.json(
          {
            error: 'api_in_use',
            message: '1 model uses this API.',
            pinnedBy: [{ type: 'model', id: 'm2', name: 'Late model', visibility: 'unreleased' }],
          },
          { status: 409 },
        ),
      ),
    );
    const panel = await open();
    await userEvent.type(within(panel).getByLabelText(/Type stripe to confirm/), 'stripe');
    await userEvent.click(within(panel).getByRole('button', { name: 'Remove stripe' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'Models or sets use this API now',
    );
    expect(within(panel).getByRole('list', { name: /use this API/ })).toHaveTextContent(
      'Late model',
    );
    expect(within(panel).getByRole('button', { name: 'Remove stripe' })).toBeDisabled();
  });

  it('shows the answer of a refusal and keeps the panel open', async () => {
    server.use(
      removal([]),
      http.delete(`${TEST_API_BASE}/v1/apis/stripe`, () =>
        HttpResponse.json({ error: 'not_found', message: 'No such API.' }, { status: 404 }),
      ),
    );
    const panel = await open();
    await userEvent.type(within(panel).getByLabelText(/Type stripe to confirm/), 'stripe');
    await userEvent.click(within(panel).getByRole('button', { name: 'Remove stripe' }));
    expect(await within(panel).findByRole('alert')).toHaveTextContent('No such API.');
  });

  it('cancel closes the panel and removes nothing', async () => {
    server.use(removal([]));
    const panel = await open();
    await userEvent.click(within(panel).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('group', { name: /^Remove / })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Stripe API' })).toBeInTheDocument();
  });
});

describe('removedSummary', () => {
  it('names the counts above zero in plain words', () => {
    expect(
      removedSummary({ documents: 12, releaseNotes: 2, packageMeta: 0, builds: 1, api: 1 }),
    ).toBe('documents 12, release notes 2, builds 1');
  });
});
