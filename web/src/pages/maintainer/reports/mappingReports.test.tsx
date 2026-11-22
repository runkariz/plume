import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { kindLabel, mappingStatusLabel, mappingStatusTone, routeShort } from './mappingLabels';
import { excerptAround } from './QuoteInDoc';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_test_token_value');
});
afterEach(() => authStore.signOut());

describe('labels', () => {
  it('names statuses, kinds and routes; a value it does not know is shown as written', () => {
    expect(mappingStatusLabel('routed')).toBe('Routed');
    expect(mappingStatusLabel('suspended-later')).toBe('suspended-later');
    expect(mappingStatusTone('accepted')).toBe('ok');
    expect(kindLabel('model-field-missing')).toBe('Field missing from the model');
    expect(routeShort('stream')).toBe('Stream');
    expect(routeShort('somewhere')).toBe('somewhere');
  });
});

describe('excerptAround', () => {
  const text = `${'a'.repeat(300)} the quote here ${'b'.repeat(300)}`;
  it('marks the quote with context on both sides, cut with a sign', () => {
    const e = excerptAround(text, 'the quote here');
    expect(e?.match).toBe('the quote here');
    expect(e?.cutBefore).toBe(true);
    expect(e?.cutAfter).toBe(true);
    expect(e?.before.length).toBeLessThanOrEqual(160);
  });
  it('is null when the quote is not in the text or empty', () => {
    expect(excerptAround('some text', 'absent')).toBeNull();
    expect(excerptAround('some text', '   ')).toBeNull();
  });
  it('has no cut signs when the quote is near both ends', () => {
    const e = excerptAround('short text with a quote in it', 'a quote');
    expect(e?.cutBefore).toBe(false);
    expect(e?.cutAfter).toBe(false);
  });
});

describe('the mapping reports list', () => {
  it('has the tab next to reported questions and lists most reported first', async () => {
    renderApp('/maintainer/mapping-reports');
    const tabs = screen.getByRole('navigation', { name: 'Kinds of reports' });
    expect(within(tabs).getByRole('link', { name: 'Mapping reports' })).toHaveClass('on');
    expect(within(tabs).getByRole('link', { name: 'Reported questions' })).toHaveAttribute(
      'href',
      '/maintainer/reports',
    );
    const list = await screen.findByRole('list', { name: 'Mapping reports' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent('Inventory › quantity_available');
    expect(rows[0]).toHaveTextContent('3 reports');
    expect(rows[0]).toHaveTextContent('suggestion valid');
    expect(within(list).getByText('suggestion failed')).toBeInTheDocument();
    expect(within(list).getAllByText('no suggestion')).toHaveLength(2);
    expect(within(list).getByText('Routed: Owner')).toBeInTheDocument();
    expect(within(list).getByText('verified')).toBeInTheDocument();
  });

  it('filters by status, API, kind and concept, in the URL', async () => {
    const { router } = renderApp('/maintainer/mapping-reports');
    await screen.findByRole('list', { name: 'Mapping reports' });
    await userEvent.click(screen.getByRole('radio', { name: 'Accepted' }));
    await waitFor(() => expect(router.state.location.search).toBe('?status=accepted'));
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Mapping reports' })).getAllByRole('listitem'),
      ).toHaveLength(1),
    );
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.selectOptions(screen.getByLabelText('Kind'), 'model-field-missing');
    await waitFor(() => expect(router.state.location.search).toBe('?kind=model-field-missing'));
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Mapping reports' })).getAllByRole('listitem'),
      ).toHaveLength(1),
    );
    await userEvent.selectOptions(screen.getByLabelText('Kind'), '');
    await userEvent.type(screen.getByLabelText('Concept'), 'product/variant');
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => expect(router.state.location.search).toBe('?concept=product%2Fvariant'));
  });

  it('says reporting is off, and says nothing matches', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/maintainer/mapping-reports`, () =>
        HttpResponse.json({ reports: [], enabled: false }),
      ),
    );
    renderApp('/maintainer/mapping-reports');
    expect(await screen.findByText('Reports are off on this server')).toBeInTheDocument();
    expect(screen.getByText('No mapping has been reported yet.')).toBeInTheDocument();
  });
});

describe('one mapping report', () => {
  const open = '/maintainer/mapping-reports/mr-1a2b3c4d5e';

  it('shows the problem, current against suggested, the citation with the quote marked, the validator', async () => {
    renderApp(open);
    const compare = await screen.findByRole('region', { name: 'Current and suggested mapping' });
    expect(within(compare).getByRole('region', { name: 'Current mapping' })).toHaveTextContent(
      'variants[].inventory_quantity',
    );
    const suggested = within(compare).getByRole('region', { name: 'Suggested mapping' });
    expect(suggested).toHaveTextContent('inventory_levels[].available');
    expect(suggested).toHaveTextContent('GET /admin/api/{version}/inventory_levels.json');
    // the quote is marked inside the cited document's own text
    await waitFor(() => {
      const mark = within(compare).getByText('Total amount billed for the order.', {
        selector: 'mark',
      });
      expect(mark.closest('blockquote')).toHaveTextContent('Sample text for this document');
    });
    expect(
      within(compare).getByRole('link', { name: 'endpoint:GET~/orders.json' }),
    ).toHaveAttribute(
      'href',
      `/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/orders.json')}`,
    );
    const validator = within(compare).getByRole('group', { name: 'Validator result' });
    expect(validator).toHaveTextContent('Passed the validator');
    // notes and the count
    expect(screen.getByText('3 reports')).toBeInTheDocument();
    expect(
      within(screen.getByRole('list', { name: 'Notes on this report' })).getAllByRole('listitem'),
    ).toHaveLength(2);
  });

  it('a verified absence says "Not available on <api>" and what it must not be mapped from', async () => {
    renderApp('/maintainer/mapping-reports/mr-8d7c6b5a4e');
    const suggested = await screen.findByRole('region', { name: 'Suggested mapping' });
    expect(suggested).toHaveTextContent('Not available on shopify');
    expect(suggested).toHaveTextContent('Not fromvariants[].inventory_quantity');
    // no empty "Source" line for an absence
    expect(within(suggested).queryByText('Source')).not.toBeInTheDocument();
    // the quote (the notFrom field's own description) is still marked in its document
    await waitFor(() =>
      expect(
        within(screen.getByRole('region', { name: 'Current and suggested mapping' })).getByText(
          'Total amount billed for the order.',
          { selector: 'mark' },
        ),
      ).toBeInTheDocument(),
    );
  });

  it('a failed suggestion is "not kept", with the validator reason, and cannot be accepted', async () => {
    renderApp('/maintainer/mapping-reports/mr-9z8y7x6w5v');
    const compare = await screen.findByRole('region', { name: 'Current and suggested mapping' });
    expect(
      within(compare).getByText(/Not kept: the suggestion failed the validator/),
    ).toBeInTheDocument();
    expect(within(compare).getByRole('group', { name: 'Validator result' })).toHaveTextContent(
      'FIELD_NOT_FOUND: variation_id is not a field of the WooCommerce package',
    );
    const decide = screen.getByRole('form', { name: 'Decide' });
    await userEvent.type(within(decide).getByLabelText('Reason'), 'checking');
    expect(within(decide).getByRole('button', { name: 'Accept' })).toBeDisabled();
    expect(within(decide).getByRole('button', { name: 'Reject' })).toBeEnabled();
  });

  it('a citation without a quote says why', async () => {
    renderApp('/maintainer/mapping-reports/mr-5t4s3r2q1p');
    expect(
      await screen.findByText(/cited without quote: the description is only a label/),
    ).toBeInTheDocument();
    const verified = screen.getByRole('region', { name: 'Verified mapping' });
    expect(verified).toHaveTextContent('verified (user report mr-5t4s3r2q1p)');
    expect(within(verified).getByText('Active')).toBeInTheDocument();
  });

  it('every action needs a reason but reopen; accept makes a verified mapping', async () => {
    renderApp(open);
    const decide = await screen.findByRole('form', { name: 'Decide' });
    const accept = within(decide).getByRole('button', { name: 'Accept' });
    expect(accept).toBeDisabled(); // no reason yet
    expect(within(decide).getByRole('button', { name: 'Route' })).toBeDisabled();
    expect(within(decide).queryByRole('button', { name: 'Reopen' })).not.toBeInTheDocument();
    await userEvent.type(
      within(decide).getByLabelText('Reason'),
      'Per-location is what clients need.',
    );
    await userEvent.click(accept);
    expect(
      await within(decide).findByText('Accepted: it is now a verified mapping.'),
    ).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: 'Verified mapping' })).toBeInTheDocument();
    expect(within(decide).getByRole('button', { name: 'Reopen' })).toBeEnabled();
  });

  it('rejects with a reason (readers see it) and routes to a target', async () => {
    renderApp(open);
    const decide = await screen.findByRole('form', { name: 'Decide' });
    expect(
      within(decide).getByText(/Readers see the reason of a rejected report/),
    ).toBeInTheDocument();
    await userEvent.type(within(decide).getByLabelText('Reason'), 'Not a mapping problem.');
    await userEvent.selectOptions(within(decide).getByLabelText('Route to'), 'stream');
    await userEvent.click(within(decide).getByRole('button', { name: 'Route' }));
    expect(await within(decide).findByText('Routed to Stream.')).toBeInTheDocument();
    expect(screen.getAllByText('Routed: Stream').length).toBeGreaterThan(0);
  });

  it('shows the server error when accept is refused', async () => {
    server.use(
      http.patch(`${TEST_API_BASE}/v1/maintainer/mapping-reports/:id`, () =>
        HttpResponse.json(
          { error: 'refused', code: 'report_refused', message: 'no valid suggestion' },
          { status: 400 },
        ),
      ),
    );
    renderApp(open);
    const decide = await screen.findByRole('form', { name: 'Decide' });
    await userEvent.type(within(decide).getByLabelText('Reason'), 'x');
    await userEvent.click(within(decide).getByRole('button', { name: 'Accept' }));
    expect(await within(decide).findByRole('alert')).toHaveTextContent('The server refused it');
  });

  it('an unknown report is "not found"', async () => {
    renderApp('/maintainer/mapping-reports/mr-nope');
    expect(await screen.findByText('Mapping report not found')).toBeInTheDocument();
  });
});

describe('verified mappings on a model page (maintainer)', () => {
  it('lists them as "verified (user report #id)", linked to the report', async () => {
    renderApp('/models/snap_8f3a21');
    const card = await screen.findByRole('region', { name: 'Verified mappings' });
    expect(card).toHaveTextContent('tracked');
    expect(
      within(card).getByRole('link', { name: 'verified (user report mr-5t4s3r2q1p)' }),
    ).toHaveAttribute('href', '/maintainer/mapping-reports/mr-5t4s3r2q1p');
  });

  it('shows a verified absence as "not available on <api>"', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/maintainer/verified-mappings`, () =>
        HttpResponse.json({
          mappings: [
            {
              id: 'vm-1',
              concept: 'inventory/stock',
              canonicalField: 'low_stock_threshold',
              api: 'shopify',
              paths: [],
              fetch: null,
              notAvailable: true,
              notFrom: ['variants[].inventory_quantity'],
              evidence: [],
              build: 'b-2026-11-14',
              reportId: 'mr-8d7c6b5a4e',
              suspended: false,
              suspendedReason: null,
            },
          ],
        }),
      ),
    );
    renderApp('/models/snap_8f3a21');
    const card = await screen.findByRole('region', { name: 'Verified mappings' });
    expect(card).toHaveTextContent('not available on shopify');
    expect(card).toHaveTextContent('variants[].inventory_quantity');
  });

  it('is not shown to a reader, nor when there is no concept or nothing verified', async () => {
    authStore.signOut();
    renderApp('/models/snap_8f3a21');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: 'Verified mappings' })).not.toBeInTheDocument();
  });
});
