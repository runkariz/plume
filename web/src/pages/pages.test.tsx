import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server, TEST_API_BASE } from '@/test/server';
import { renderApp } from '@/test/render';

describe('Home (W1 stub)', () => {
  it('shows a loading state, then the APIs', async () => {
    renderApp('/');
    expect(screen.getByRole('status')).toHaveTextContent('Loading APIs');
    expect(await screen.findByText('Shopify Admin REST')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows the empty state when there are no APIs', async () => {
    server.use(http.get(`${TEST_API_BASE}/v1/apis`, () => HttpResponse.json({ items: [] })));
    renderApp('/');
    expect(await screen.findByText('No APIs yet')).toBeInTheDocument();
  });

  it('shows the error state and retries', async () => {
    server.use(
      http.get(
        `${TEST_API_BASE}/v1/apis`,
        () => HttpResponse.json({ detail: 'database is down' }, { status: 503 }),
        { once: true },
      ),
    );
    renderApp('/');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('database is down');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Shopify Admin REST')).toBeInTheDocument();
  });
});

describe('Kit page', () => {
  it('renders every component group', () => {
    renderApp('/kit');
    expect(screen.getByRole('heading', { name: /buttons/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Maintainer key')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Category' })).toBeInTheDocument();
  });

  it('filter pills expose pressed state', async () => {
    renderApp('/kit');
    const pill = screen.getByRole('button', { name: 'Payments' });
    expect(pill).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(pill);
    expect(pill).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('Routing', () => {
  it('renders placeholders for later slices', () => {
    renderApp('/maintainer');
    expect(screen.getByText('Maintainer sign-in')).toBeInTheDocument();
  });

  it('renders not found', () => {
    renderApp('/nope');
    expect(screen.getByText('Page not found')).toBeInTheDocument();
  });
});

describe('Theme toggle', () => {
  it('flips data-theme and remembers it', async () => {
    document.documentElement.dataset.theme = 'light';
    renderApp('/');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(localStorage.getItem('plume-theme')).toBe('dark');
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument();
  });
});
