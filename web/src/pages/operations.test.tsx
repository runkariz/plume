import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

/** Mirakl's three GET /{file_path} downloads: their ids carry the operation after "@". */
const OPS = ['get-of54', 'get-or15', 'get-tl05'];
const idOf = (op: string) => `endpoint:GET~/{file_path}@${op}`;

describe('two operations at one METHOD + path', () => {
  it('Browse rows keep the same method and path, say which operation each is, and link by the encoded id', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/items`, () =>
        HttpResponse.json({
          items: OPS.map((op) => ({
            id: idOf(op),
            kind: 'endpoint',
            title: `Download ${op}`,
            method: 'GET',
            path: '/{file_path}',
          })),
          total: 3,
        }),
      ),
    );
    renderApp('/apis/shopify');
    await screen.findByText('Download get-or15');
    const links = [...document.querySelectorAll('.ep-link')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(
      OPS.map((op) => `/apis/shopify/documents/${encodeURIComponent(idOf(op))}`),
    );
    const rows = document.querySelectorAll('.ep');
    expect(rows).toHaveLength(3);
    OPS.forEach((op, i) => expect(rows[i]).toHaveTextContent(`· ${op}`));
  });

  it('the document page asks for the encoded id, shows the method and path from the document, and the operation', async () => {
    let asked = '';
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/:id/documents/:docId`, ({ request }) => {
        asked = new URL(request.url).pathname;
        return HttpResponse.json({
          api: 'mirakl',
          build: 'b-1',
          docsAsOf: '2026-11-14',
          id: idOf('get-or15'),
          kind: 'endpoint',
          title: 'Download an order document',
          resource: 'orders',
          method: 'GET',
          path: '/{file_path}',
          deprecated: false,
          complete: true,
          sourceUrl: null,
          anchor: null,
          text: 'Downloads a file.',
          fields: [],
          scopes: [],
        });
      }),
    );
    renderApp(`/apis/mirakl/documents/${encodeURIComponent(idOf('get-or15'))}`);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Download an order document' }),
    ).toBeInTheDocument();
    expect(asked).toBe(`/v1/apis/mirakl/documents/${encodeURIComponent(idOf('get-or15'))}`);
    expect(screen.getByText('GET')).toBeInTheDocument();
    expect(screen.getByText('/{file_path}')).toBeInTheDocument();
    expect(screen.getByText('· get-or15')).toBeInTheDocument();
  });

  it('check-call names the matched operation and lists the alternatives at the same method and path', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/check-call`, () =>
        HttpResponse.json({
          api: 'mirakl',
          build: 'b-1',
          verdict: 'documented',
          complete: true,
          matched: { id: idOf('get-or15'), method: 'GET', path: '/{file_path}' },
          paramChecks: [],
          checked: { endpoints: 10, models: 2 },
          alternatives: ['get-of54', 'get-tl05'],
        }),
      ),
    );
    renderApp('/apis/shopify/try');
    await userEvent.click(await screen.findByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    expect(await screen.findByText('Documented')).toBeInTheDocument();
    expect(screen.getByText('· get-or15')).toBeInTheDocument();
    const alt = screen.getByText(/Other operations at the same method and path/);
    expect(within(alt).getByText('get-of54')).toBeInTheDocument();
    expect(within(alt).getByText('get-tl05')).toBeInTheDocument();
  });

  it('without alternatives (an older server, or one operation) nothing is said', async () => {
    renderApp('/apis/shopify/try');
    await userEvent.click(await screen.findByRole('radio', { name: 'Check call' }));
    await userEvent.click(screen.getByRole('button', { name: 'Check' }));
    await screen.findByText('Documented');
    expect(
      screen.queryByText(/Other operations at the same method and path/),
    ).not.toBeInTheDocument();
  });
});
