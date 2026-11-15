import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server, TEST_API_BASE } from '@/test/server';
import { renderApp } from '@/test/render';

describe('Home', () => {
  it('shows skeleton cards while loading', () => {
    renderApp('/');
    expect(screen.getByRole('status')).toHaveTextContent('Loading APIs');
  });

  it('lists the APIs with stats, date and quality chip', async () => {
    renderApp('/');
    const shopifyLink = await screen.findByRole('link', { name: 'Shopify Admin REST' });
    const shopify = shopifyLink.closest('article') as HTMLElement;
    expect(within(shopify).getByText('E-commerce')).toBeInTheDocument();
    expect(within(shopify).getByText('137')).toBeInTheDocument();
    expect(within(shopify).getByText('Docs as of 14 Nov 2026')).toBeInTheDocument();
    expect(within(shopify).getByText('Recall@5 0.94')).toBeInTheDocument();
    expect(shopifyLink).toHaveAttribute('href', '/apis/shopify');
    const github = screen
      .getByRole('link', { name: 'GitHub REST' })
      .closest('article') as HTMLElement;
    expect(within(github).getByText('Recall@5 0.89').className).toContain('ok');
    const slack = screen
      .getByRole('link', { name: 'Slack Web API' })
      .closest('article') as HTMLElement;
    expect(within(slack).getByText('Recall@5 0.88').className).toContain('warn');
    const notion = screen
      .getByRole('link', { name: 'Notion API' })
      .closest('article') as HTMLElement;
    expect(within(notion).getByText('Updating · 62%')).toBeInTheDocument();
  });

  it('shows category chips with counts and filters by them', async () => {
    renderApp('/');
    await screen.findByRole('link', { name: 'Shopify Admin REST' });
    const group = screen.getByRole('group', { name: 'Filter by category' });
    expect(within(group).getByRole('button', { name: 'All · 6' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(within(group).getByRole('button', { name: 'Communication · 2' }));
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Stripe API' })).not.toBeInTheDocument();
  });

  it('filters by the search box and shows a no-match state', async () => {
    renderApp('/');
    await screen.findByRole('link', { name: 'Stripe API' });
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search APIs' }), 'stripe');
    expect(screen.queryByRole('link', { name: 'Slack Web API' })).not.toBeInTheDocument();
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Search APIs' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search APIs' }), 'zzzz');
    expect(screen.getByText('No APIs match')).toBeInTheDocument();
  });

  it('"/" focuses the search box', async () => {
    renderApp('/');
    await userEvent.keyboard('/');
    expect(screen.getByRole('searchbox', { name: 'Search APIs' })).toHaveFocus();
  });

  it('shows the empty state', async () => {
    server.use(http.get(`${TEST_API_BASE}/v1/apis`, () => HttpResponse.json({ items: [] })));
    renderApp('/');
    expect(await screen.findByText('No APIs yet')).toBeInTheDocument();
  });

  it('shows the error state and retries', async () => {
    server.use(
      http.get(
        `${TEST_API_BASE}/v1/apis`,
        () => HttpResponse.json({ detail: 'db down' }, { status: 503 }),
        {
          once: true,
        },
      ),
    );
    renderApp('/');
    expect(await screen.findByRole('alert')).toHaveTextContent('db down');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('link', { name: 'Shopify Admin REST' })).toBeInTheDocument();
  });
});
