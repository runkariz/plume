import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import type { ModelSnapshot } from '@/api/types';
import { createHandlers } from '@/mocks/handlers';
import { productSnapshot } from '@/mocks/modelData';
import { UNRELEASED } from '@/mocks/modelStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { MappingDetail } from './MappingDetail';
import { groupWarnings, warningSearch, warningsFor, warningSummary } from './warnings';

const W = (field: string, api: string | null, code = 'WRITE_ONLY_SOURCE') => ({
  code,
  field,
  api,
  message: `${field} message`,
});
const snap = {
  ...productSnapshot,
  warnings: [W('sku', 'mirakl'), W('title', 'mirakl'), W('sku', 'woocommerce')],
} as ModelSnapshot;

beforeEach(() => server.use(...createHandlers(TEST_API_BASE)));
afterEach(() => authStore.signOut());

describe('warning helpers', () => {
  it('say how many mappings cite only a request body, and read an unknown code generically', () => {
    expect(warningSummary('WRITE_ONLY_SOURCE', [W('a', null)])).toBe(
      '1 mapping cites only a request body',
    );
    expect(warningSummary('WRITE_ONLY_SOURCE', [W('a', null), W('b', null), W('c', null)])).toBe(
      '3 mappings cite only a request body',
    );
    expect(warningSummary('SOMETHING_NEW', [W('a', null, 'SOMETHING_NEW')])).toBe(
      '1 warning: something new',
    );
  });

  it('group by code in the order the server sent them; none when there are none (or an older server)', () => {
    const g = groupWarnings([W('a', null), W('b', null, 'X_Y'), W('c', null)]);
    expect(g.map((x) => [x.code, x.items.length])).toEqual([
      ['WRITE_ONLY_SOURCE', 2],
      ['X_Y', 1],
    ]);
    expect(groupWarnings([])).toEqual([]);
    expect(groupWarnings(undefined)).toEqual([]);
  });

  it('belong to a mapping: the field, and the API when the warning names one', () => {
    expect(warningsFor(snap, 'sku', 'mirakl').map((w) => w.api)).toEqual(['mirakl']);
    expect(warningsFor(snap, 'sku', 'shopify')).toEqual([]);
    const any = { ...snap, warnings: [W('sku', null)] } as ModelSnapshot;
    expect(warningsFor(any, 'sku', 'shopify')).toHaveLength(1); // no API named: it is about the field
  });

  it('link to the mapping only when the model has it (never to something that is not there)', () => {
    expect(warningSearch(snap, W('sku', 'mirakl'))).toBe('?field=sku&api=mirakl');
    expect(warningSearch(snap, W('sku', null))).toMatch(/^\?field=sku&api=/);
    expect(warningSearch(snap, W('nope', 'mirakl'))).toBeNull();
    expect(warningSearch(snap, W('sku', 'unknown-api'))).toBeNull();
    expect(warningSearch(snap, { code: 'X', message: 'm' })).toBeNull();
  });
});

describe('the mapping detail', () => {
  it('says so under the mapping a warning is about, as text', () => {
    render(<MappingDetail snap={snap} sel={{ field: 'sku', apiId: 'mirakl' }} />);
    expect(screen.getByRole('note')).toHaveTextContent('sku message');
  });
  it('says nothing for a mapping without one', () => {
    render(<MappingDetail snap={snap} sel={{ field: 'sku', apiId: 'shopify' }} />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});

describe('the model page and the review banner', () => {
  it('list the warnings, say how many in the review banner, and link each to its mapping', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    const { router } = renderApp(`/models/${UNRELEASED}`);
    const list = await screen.findByRole('region', { name: '3 mappings cite only a request body' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    // the review banner says it too, with a way to the list
    const banner = screen
      .getByText('Unreleased: waiting for your review')
      .closest('div') as HTMLElement;
    expect(banner.parentElement).toHaveTextContent(
      'Before you release: 3 mappings cite only a request body',
    );
    expect(
      within(banner.parentElement as HTMLElement).getByRole('link', { name: 'See the list' }),
    ).toHaveAttribute('href', '#model-warnings');
    // a warning links to the mapping it is about
    await userEvent.click(within(list).getAllByRole('link', { name: 'title' })[0] as HTMLElement);
    expect(router.state.location.search).toContain('field=title');
    expect(router.state.location.search).toContain('api=mirakl');
    expect(await screen.findByRole('note')).toHaveTextContent(
      'product_title is documented only in the request body',
    );
  });

  it('show nothing for a model without warnings, and the field as plain text when its mapping is gone', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, () =>
        HttpResponse.json({
          ...productSnapshot,
          id: 'm-w',
          visibility: 'official',
          warnings: [W('gone-field', 'mirakl')],
        }),
      ),
    );
    renderApp('/models/m-w');
    const list = await screen.findByRole('region', { name: '1 mapping cites only a request body' });
    expect(within(list).queryByRole('link')).not.toBeInTheDocument();
    expect(within(list).getByText('gone-field')).toBeInTheDocument();
  });

  it('are absent without them: no banner', async () => {
    renderApp('/models/m-none');
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/:id`, () =>
        HttpResponse.json({ ...productSnapshot, id: 'm-none', visibility: 'official' }),
      ),
    );
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByText('Check these mappings')).not.toBeInTheDocument();
  });
});
