import { render, screen, within } from '@testing-library/react';
import { DocConflicts, placeOf } from '@/components/DocConflicts';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('placeOf', () => {
  it('says where a statement stands', () => {
    expect(placeOf('description')).toEqual({ label: 'the description', url: null });
    expect(placeOf('param:limit')).toEqual({ label: 'parameter limit', url: null });
    expect(placeOf('page:https://a.com/x')).toEqual({ label: 'page', url: 'https://a.com/x' });
    expect(placeOf('something-new')).toEqual({ label: 'something-new', url: null });
  });
});

describe('conflicting statements', () => {
  it('lists every statement of a limit with its place, examples marked, no value picked', async () => {
    renderApp(`/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/orders.json')}`);
    const card = await screen.findByRole('region', { name: 'Conflicting statements' });
    expect(card).toHaveTextContent('The docs state different values for page size:');
    const list = within(card).getByRole('list', { name: 'Statements about page size' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('Returns up to 128 items per page. in the description');
    expect(items[1]).toHaveTextContent('The maximum is 256. in parameter limit');
    // an example is marked, a page is a link that opens in a new tab
    expect(within(items[2] as HTMLElement).getByText('example')).toBeInTheDocument();
    expect(within(items[0] as HTMLElement).queryByText('example')).not.toBeInTheDocument();
    const link = within(items[2] as HTMLElement).getByRole('link');
    expect(link).toHaveAttribute('href', 'https://shopify.dev/docs/api/usage/pagination-rest');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('shows nothing when there are none', () => {
    expect(render(<DocConflicts conflicts={undefined} />).container).toBeEmptyDOMElement();
    expect(render(<DocConflicts conflicts={[]} />).container).toBeEmptyDOMElement();
    expect(
      render(<DocConflicts conflicts={[{ limit: 'x', statements: [] }]} />).container,
    ).toBeEmptyDOMElement();
  });

  it('a page that is not http(s) is text, never a link; the text is plain', () => {
    render(
      <DocConflicts
        conflicts={[
          {
            limit: 'rate',
            statements: [
              {
                where: 'page:javascript:alert(1)',
                quote: '<b>10 per second</b>',
                isExample: false,
              },
            ],
          },
        ]}
      />,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('<b>10 per second</b>')).toBeInTheDocument();
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument();
  });

  it('a document without conflicts has no such card', async () => {
    renderApp(`/apis/shopify/documents/${encodeURIComponent('guide:pagination')}`);
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.queryByRole('region', { name: 'Conflicting statements' }),
    ).not.toBeInTheDocument();
  });
});
