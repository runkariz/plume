import { render, screen, within } from '@testing-library/react';
import type { DocConflict } from '@/api/types';
import { DocConflicts } from '@/components/DocConflicts';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

const condition: DocConflict = {
  limit: 'field item_group_id required if item_id is not provided',
  kind: 'condition',
  field: 'item_group_id',
  statements: [{ where: 'param:item_group_id', quote: 'Required if item_id is not provided' }],
};

describe('a condition', () => {
  it('is not a disagreement: its own card, worded as a condition on the field', () => {
    render(<DocConflicts conflicts={[condition]} />);
    const card = screen.getByRole('region', { name: 'Conditions' });
    expect(card).toHaveTextContent('Condition on item_group_id (send it only when this applies):');
    expect(card).toHaveTextContent('Required if item_id is not provided');
    expect(card).toHaveTextContent('in parameter item_group_id');
    expect(
      screen.queryByRole('region', { name: 'Conflicting statements' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/disagree\b|different values/)).not.toBeInTheDocument();
    expect(screen.queryByText('The docs disagree')).not.toBeInTheDocument();
  });

  it('without a field is worded on what the server calls it', () => {
    render(<DocConflicts conflicts={[{ ...condition, field: null, limit: 'the update mask' }]} />);
    expect(screen.getByRole('region', { name: 'Conditions' })).toHaveTextContent(
      'Condition on the update mask (send it only when this applies):',
    );
  });
});

describe('a property-level disagreement', () => {
  const statements = [
    { where: 'page', quote: 'a', sourceUrl: 'https://x.com/a' },
    { where: 'description', quote: 'b' },
  ];

  it('is headed by its field, with what the server calls it underneath', () => {
    const about = 'transaction_type values: one page allows SALE or REFUND, another more';
    render(
      <DocConflicts
        conflicts={[
          { limit: about, field: 'transaction_type', statements },
          { limit: 'the allowed values', field: 'items[].status', statements },
          { limit: 'items.status', field: 'items[].status', statements },
        ]}
      />,
    );
    const card = screen.getByRole('region', { name: 'Conflicting statements' });
    expect(
      within(card)
        .getAllByRole('heading', { level: 3 })
        .map((h) => h.textContent),
    ).toEqual([
      'The docs state different values for transaction_type:',
      'The docs state different values for items[].status:',
      'The docs state different values for items[].status:',
    ]);
    expect(within(card).getByText(about)).toBeInTheDocument();
    expect(within(card).getByText('the allowed values')).toBeInTheDocument();
    // the same name is not said twice
    expect(within(card).queryByText('items.status')).not.toBeInTheDocument();
    // a statement whose place is only "page" says so, with its source link
    expect(within(card).getAllByRole('listitem')[0]).toHaveTextContent(
      'in a documentation page (source)',
    );
  });

  it('without a field is headed by the limit as before', () => {
    render(<DocConflicts conflicts={[{ limit: 'the page size', statements }]} />);
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
      'The docs state different values for the page size:',
    );
  });
});

describe('on a document page', () => {
  it('shows the disagreements and the conditions apart', async () => {
    renderApp(`/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/orders.json')}`);
    const disagree = await screen.findByRole('region', { name: 'Conflicting statements' });
    const conditions = screen.getByRole('region', { name: 'Conditions' });
    expect(disagree).toHaveTextContent('different values for orders[].financial_status:');
    expect(disagree).not.toHaveTextContent('Required if since_id is not provided.');
    expect(conditions).toHaveTextContent('Condition on ids (send it only when this applies):');
  });
});
