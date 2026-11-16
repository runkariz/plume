import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_ok', 'maintainer');
});
afterEach(() => authStore.signOut());

const row = async (name: string) =>
  (await screen.findByRole('button', { name: `Rename ${name}` })).closest('li') as HTMLElement;

describe('a maintainer renames an API for display', () => {
  it('saves a name, shows it everywhere the list shows it, and marks it renamed', async () => {
    renderApp('/maintainer');
    const li = await row('Shopify Admin REST');
    await userEvent.click(within(li).getByRole('button', { name: 'Rename Shopify Admin REST' }));
    const input = screen.getByLabelText('Display name of shopify');
    expect(input).toHaveValue('Shopify Admin REST');
    // unchanged: nothing to save
    expect(screen.getByRole('button', { name: 'Save name' })).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, '  Shopify   Admin  ');
    await userEvent.click(screen.getByRole('button', { name: 'Save name' }));
    const renamed = await row('Shopify Admin');
    expect(renamed).toHaveTextContent('Shopify Admin');
    expect(within(renamed).getByText('Renamed')).toBeInTheDocument();
  });

  it('"Use the package name" clears the override', async () => {
    renderApp('/maintainer');
    let li = await row('Shopify Admin REST');
    await userEvent.click(within(li).getByRole('button', { name: /^Rename/ }));
    await userEvent.clear(screen.getByLabelText('Display name of shopify'));
    await userEvent.type(screen.getByLabelText('Display name of shopify'), 'My Shopify');
    await userEvent.click(screen.getByRole('button', { name: 'Save name' }));
    li = await row('My Shopify');
    await userEvent.click(within(li).getByRole('button', { name: /^Rename/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Use the package name' }));
    li = await row('Shopify Admin REST');
    expect(within(li).queryByText('Renamed')).not.toBeInTheDocument();
  });

  it("shows the server's refusal and keeps the form open", async () => {
    server.use(
      http.put(`${TEST_API_BASE}/v1/apis/shopify/display`, () =>
        HttpResponse.json(
          {
            error: 'conflict',
            code: 'invalid_input',
            message: 'The name must be 1 to 80 characters.',
          },
          { status: 409 },
        ),
      ),
    );
    renderApp('/maintainer');
    const li = await row('Shopify Admin REST');
    await userEvent.click(within(li).getByRole('button', { name: /^Rename/ }));
    await userEvent.type(screen.getByLabelText('Display name of shopify'), ' x');
    await userEvent.click(screen.getByRole('button', { name: 'Save name' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The name must be 1 to 80 characters.',
    );
    expect(screen.getByLabelText('Display name of shopify')).toBeInTheDocument();
  });

  it('cancel closes the form without saving, and the name is capped at 80 characters', async () => {
    renderApp('/maintainer');
    const li = await row('Shopify Admin REST');
    await userEvent.click(within(li).getByRole('button', { name: /^Rename/ }));
    expect(screen.getByLabelText('Display name of shopify')).toHaveAttribute('maxlength', '80');
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.queryByLabelText('Display name of shopify')).not.toBeInTheDocument(),
    );
  });
});
