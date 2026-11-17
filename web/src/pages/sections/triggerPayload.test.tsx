import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { triggerDetailFor } from '@/mocks/sectionData';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

describe('trigger payload', () => {
  it('shows the payload fields like a model and the sample behind a toggle', async () => {
    renderApp('/apis/shopify/triggers/orders%2Fcreate');
    const head = await screen.findByRole('region', { name: 'Payload' });
    expect(head).toHaveTextContent('Schema: orders-create.payload.schema.json');
    const fields = screen.getByRole('region', { name: 'Payload fields' });
    expect(within(fields).getByText('line_items[].sku')).toBeInTheDocument();
    expect(within(fields).getByText('required')).toBeInTheDocument();
    // the allowed values come with the field, as on a model
    expect(fields).toHaveTextContent('pending');
    // the sample is plain JSON text in a collapsed block
    const sample = screen.getByLabelText('Sample payload');
    expect(sample).toHaveTextContent('"sku": "A-1"');
    expect(sample.closest('details')).not.toHaveAttribute('open');
    // the refs are said once (in Payload), not again under "What it is"
    expect(
      within(screen.getByRole('region', { name: 'Event' })).queryByText('sampleRef'),
    ).toBeNull();
  });

  it('links to the model when the payload is a model, with no fields table', async () => {
    renderApp('/apis/shopify/triggers/app%2Funinstalled');
    const head = await screen.findByRole('region', { name: 'Payload' });
    expect(within(head).getByRole('link', { name: 'Order' })).toHaveAttribute(
      'href',
      '/apis/shopify/documents/model%3Aorder',
    );
    expect(screen.queryByRole('region', { name: 'Payload fields' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Sample payload')).not.toBeInTheDocument();
  });

  it('says so, with the refs as text, when the server could not read them', async () => {
    renderApp('/apis/shopify/triggers/app%2Fscopes_update');
    const head = await screen.findByRole('region', { name: 'Payload' });
    expect(head).toHaveTextContent('could not read it');
    expect(head).toHaveTextContent('nope.json');
    expect(screen.queryByRole('region', { name: 'Payload fields' })).not.toBeInTheDocument();
  });

  it('has no Payload section when the payload is null or absent', async () => {
    const base = triggerDetailFor('shopify', 'orders/create');
    for (const payload of [null, undefined]) {
      server.use(
        http.get(`${TEST_API_BASE}/v1/apis/shopify/triggers/*`, () =>
          HttpResponse.json({ ...base, payload }),
        ),
      );
      const { unmount } = renderApp('/apis/shopify/triggers/orders%2Fcreate');
      await screen.findByRole('heading', { level: 1, name: 'orders/create' });
      expect(screen.queryByRole('region', { name: 'Payload' })).not.toBeInTheDocument();
      expect(screen.queryByRole('region', { name: 'Payload fields' })).not.toBeInTheDocument();
      unmount();
    }
  });

  it('a sample alone (no schema) is still shown', async () => {
    const base = triggerDetailFor('shopify', 'orders/create');
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/triggers/*`, () =>
        HttpResponse.json({
          ...base,
          payload: {
            schemaRef: null,
            sampleRef: 's.json',
            schema: null,
            sample: { a: 1 },
            model: null,
            fields: [],
          },
        }),
      ),
    );
    renderApp('/apis/shopify/triggers/orders%2Fcreate');
    expect(await screen.findByLabelText('Sample payload')).toHaveTextContent('"a": 1');
    expect(screen.queryByText(/could not read/)).not.toBeInTheDocument();
  });
});
