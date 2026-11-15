import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { DEMO_OWNER_KEY } from '@/mocks/modelStore';
import { createHandlers } from '@/mocks/handlers';
import { SET_OWNER_KEY } from '@/mocks/setStore';
import { readOwnerKeys } from '@/lib/ownerKeys';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
});

async function open() {
  const view = renderApp('/models');
  const region = await screen.findByRole('region', { name: 'Add an owner key' });
  await userEvent.click(within(region).getByText(/Have an owner key/));
  return { region, ...view };
}
const paste = async (region: HTMLElement, key: string) => {
  const box = within(region).getByLabelText('Owner key');
  await userEvent.click(box);
  await userEvent.paste(key);
  await userEvent.click(within(region).getByRole('button', { name: 'Add key' }));
};

describe('Add an owner key (Models page)', () => {
  it('lists the models of a key from another browser, and keeps the key here', async () => {
    const { region, router } = await open();
    expect(screen.queryByRole('region', { name: 'Your models' })).not.toBeInTheDocument();
    await paste(region, `  ${DEMO_OWNER_KEY}  `); // surrounding spaces from a paste are ignored
    expect(await within(region).findByRole('status')).toHaveTextContent(/Added: 1 model/);
    const yours = await screen.findByRole('region', { name: 'Your models' });
    expect(within(yours).getAllByRole('link').length).toBeGreaterThan(0);
    expect(readOwnerKeys()).toEqual([DEMO_OWNER_KEY]);
    expect(within(region).getByLabelText('Owner key')).toHaveValue('');
    // the key never goes into the address
    expect(router.state.location.search).toBe('');
  });

  it('a key of model sets lists them too', async () => {
    const { region } = await open();
    await paste(region, SET_OWNER_KEY);
    expect(await within(region).findByRole('status')).toHaveTextContent(
      /Added: 0 models and 1 model set/,
    );
    expect(await screen.findByRole('region', { name: 'Your model sets' })).toBeInTheDocument();
  });

  it('does not keep a key that finds nothing (a mistyped key), and says so', async () => {
    const { region } = await open();
    await paste(region, 'ok-typo');
    expect(await within(region).findByRole('alert')).toHaveTextContent(
      'No model or model set belongs to this key',
    );
    expect(readOwnerKeys()).toEqual([]);
  });

  it('refuses a paste with spaces inside, and a key this browser already has', async () => {
    const { region } = await open();
    await paste(region, 'two words');
    expect(await within(region).findByRole('alert')).toHaveTextContent('A key has no spaces');
    await userEvent.clear(within(region).getByLabelText('Owner key'));
    localStorage.setItem('plume-owner-keys', JSON.stringify([DEMO_OWNER_KEY]));
    await paste(region, DEMO_OWNER_KEY);
    expect(await within(region).findByRole('status')).toHaveTextContent('already has that key');
  });

  it('says when the server fails, and does not keep the key', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/models/mine`, () =>
        HttpResponse.json({ error: 'internal', message: 'boom' }, { status: 500 }),
      ),
    );
    const { region } = await open();
    await paste(region, DEMO_OWNER_KEY);
    await waitFor(() =>
      expect(within(region).getByRole('alert')).toHaveTextContent(/boom|failed|error/i),
    );
    expect(readOwnerKeys()).toEqual([]);
  });

  it('sends the key in a POST body, never in the URL', async () => {
    const seen: string[] = [];
    server.events.on('request:start', ({ request }) => {
      if (request.url.includes('/mine')) seen.push(`${request.method} ${request.url}`);
    });
    const { region } = await open();
    await paste(region, DEMO_OWNER_KEY);
    await within(region).findByRole('status');
    expect(seen.length).toBeGreaterThan(0);
    for (const line of seen) {
      expect(line).toMatch(/^POST /);
      expect(line).not.toContain(DEMO_OWNER_KEY);
    }
    server.events.removeAllListeners();
  });
});
