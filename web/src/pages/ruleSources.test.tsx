import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { pageLabel, RuleSources } from '@/components/RuleSources';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('pageLabel', () => {
  it('shows host and path for people and keeps odd text as it is', () => {
    expect(pageLabel('https://shopify.dev/docs/api/')).toBe('shopify.dev/docs/api');
    expect(pageLabel('https://shopify.dev/')).toBe('shopify.dev');
    expect(pageLabel('https://a.com/x#frag')).toBe('a.com/x#frag');
    expect(pageLabel('not a url')).toBe('not a url');
  });
});

describe('rules stated on several pages', () => {
  it('shows "Stated on N pages" with the first three links, then all of them', async () => {
    renderApp('/apis/shopify/documents/guide%3Apagination');
    const card = await screen.findByRole('region', { name: 'Rule sources' });
    // one rule names a single page: not listed
    expect(within(card).queryByText('rule-single')).not.toBeInTheDocument();
    expect(within(card).getByText('Stated on 5 pages')).toBeInTheDocument();
    expect(within(card).getByText('Stated on 2 pages')).toBeInTheDocument();
    const list = within(card).getByRole('list', { name: 'Pages of rule rule-cursor-limit' });
    expect(within(list).getAllByRole('link')).toHaveLength(3);
    const first = within(list).getAllByRole('link')[0] as HTMLAnchorElement;
    expect(first).toHaveTextContent('shopify.dev/docs/api/usage/pagination-rest');
    expect(first).toHaveAttribute('href', 'https://shopify.dev/docs/api/usage/pagination-rest');
    expect(first).toHaveAttribute('target', '_blank');
    expect(first.rel).toContain('noopener');
    // the two-page rule has no button
    expect(within(card).getAllByRole('button', { name: /Show/ })).toHaveLength(1);
    await userEvent.click(within(card).getByRole('button', { name: 'Show all 5' }));
    expect(within(list).getAllByRole('link')).toHaveLength(5);
    await userEvent.click(within(card).getByRole('button', { name: 'Show the first 3' }));
    expect(within(list).getAllByRole('link')).toHaveLength(3);
  });

  it('shows nothing when ruleSources is empty or absent', async () => {
    renderApp('/apis/shopify/documents/guide%3Arate-limits');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: 'Rule sources' })).not.toBeInTheDocument();
  });

  it('shows nothing when every rule names one page (also after removing repeats)', () => {
    const { container } = render(
      <RuleSources
        sources={[
          { ruleId: 'a', urls: ['https://x.com/p'] },
          { ruleId: 'b', urls: ['https://x.com/p', 'https://x.com/p', ' '] },
        ]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(render(<RuleSources sources={[]} />).container).toBeEmptyDOMElement();
    expect(render(<RuleSources sources={undefined} />).container).toBeEmptyDOMElement();
  });

  it('never makes a link of a non-http address (it is shown as text)', () => {
    render(
      <RuleSources sources={[{ ruleId: 'a', urls: ['javascript:alert(1)', 'https://x.com/p'] }]} />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument();
  });
});
