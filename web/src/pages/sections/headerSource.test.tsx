import { render, screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { HeaderSource, headerLine } from './HeaderSource';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

const NOTE = "OAuth 2.0 standard (RFC 6750), not stated in the vendor's docs";

describe('headerLine', () => {
  it("uses the server's own format when it sends one", () => {
    expect(
      headerLine({
        headerName: 'Authorization',
        headerPrefix: 'Bearer',
        headerFormat: 'Authorization: Bearer <token>',
      }),
    ).toBe('Authorization: Bearer <token>');
    // not rebuilt: what the server says is what is shown
    expect(headerLine({ headerName: 'X', headerPrefix: 'Y', headerFormat: 'X: Y <token>' })).toBe(
      'X: Y <token>',
    );
  });

  it('has exactly one space between the prefix and the token, with or without a trailing space', () => {
    expect(headerLine({ headerName: 'Authorization', headerPrefix: 'Bearer' })).toBe(
      'Authorization: Bearer <token>',
    );
    expect(headerLine({ headerName: 'Authorization', headerPrefix: 'Bearer ' })).toBe(
      'Authorization: Bearer <token>',
    );
    expect(headerLine({ headerName: 'Authorization', headerPrefix: '  Bearer  ' })).toBe(
      'Authorization: Bearer <token>',
    );
  });
  it('is null without a header name or a prefix', () => {
    expect(headerLine({ headerName: 'X-Key', headerPrefix: null })).toBeNull();
    expect(headerLine({ headerName: 'X-Key', headerPrefix: '' })).toBeNull();
    expect(headerLine({ headerName: null, headerPrefix: 'Bearer' })).toBeNull();
  });
});

describe('HeaderSource', () => {
  it('shows the standard label in the open and never a quote', () => {
    const { container } = render(
      <HeaderSource
        scheme={{
          headerName: 'Authorization',
          headerPrefix: 'Bearer',
          headerSource: 'standard:rfc6750',
          headerNote: NOTE,
          headerEvidence: 'a quote that must not be shown',
        }}
      />,
    );
    expect(screen.getByText(NOTE)).toBeVisible();
    expect(container.querySelector('blockquote')).toBeNull();
    expect(screen.queryByText(/must not be shown/)).not.toBeInTheDocument();
  });
  it('shows the vendor quote as a quote', () => {
    const { container } = render(
      <HeaderSource
        scheme={{
          headerName: 'Authorization',
          headerPrefix: 'Bearer',
          headerSource: 'vendor',
          headerEvidence: 'Send it as a Bearer token.',
          headerNote: null,
        }}
      />,
    );
    expect(container.querySelector('blockquote')).toHaveTextContent('“Send it as a Bearer token.”');
  });
  it('shows nothing extra when the source is unknown, and no quote for an unknown source with evidence', () => {
    expect(
      render(<HeaderSource scheme={{ headerName: 'X', headerSource: null }} />).container,
    ).toBeEmptyDOMElement();
    expect(
      render(
        <HeaderSource
          scheme={{ headerName: 'X', headerSource: null, headerEvidence: 'stray quote' }}
        />,
      ).container,
    ).toBeEmptyDOMElement();
  });
});

describe('the auth pages', () => {
  it('a vendor header: the full line and the quote, on the scheme page', async () => {
    renderApp('/apis/stripe/auth/api-key');
    const how = await screen.findByRole('region', { name: 'How it works' });
    expect(within(how).getByText('Authorization: Bearer <token>')).toBeInTheDocument();
    expect(how.querySelector('blockquote')).toHaveTextContent(
      'Authenticate your account by including your secret key in the request as a Bearer token.',
    );
    expect(within(how).queryByText(NOTE)).not.toBeInTheDocument();
  });

  it('the standard header: the label is shown next to the header, no quote, one space', async () => {
    renderApp('/apis/stripe/auth/oauth2-connect');
    const how = await screen.findByRole('region', { name: 'How it works' });
    expect(within(how).getByText('Authorization: Bearer <token>')).toBeInTheDocument();
    expect(within(how).getByText(NOTE)).toBeVisible();
    expect(how.querySelector('blockquote')).toBeNull();
  });

  it('the auth list shows the line for each scheme and the label of the standard one', async () => {
    renderApp('/apis/stripe?section=auth');
    const card = await screen.findByRole('region', { name: 'Authentication' });
    expect(await within(card).findAllByText('Authorization: Bearer <token>')).toHaveLength(2);
    expect(within(card).getAllByText(NOTE)).toHaveLength(1);
  });

  it('a scheme without a header source shows only its header name', async () => {
    renderApp('/apis/shopify?section=auth');
    const card = await screen.findByRole('region', { name: 'Authentication' });
    expect(await within(card).findByText('header X-Shopify-Access-Token')).toBeInTheDocument();
    expect(within(card).queryByText(/<token>/)).not.toBeInTheDocument();
    expect(within(card).queryByText(NOTE)).not.toBeInTheDocument();
  });

  it('a server that sends headerFormat: the page shows that string', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/stripe/auth/api-key`, () =>
        HttpResponse.json({
          api: 'stripe',
          build: 'b',
          id: 'api-key',
          docId: 'auth:api-key',
          name: 'API key',
          type: 'API_KEY',
          grantType: null,
          headerName: 'Authorization',
          headerPrefix: 'Token ',
          headerFormat: 'Authorization: Token <token>',
          headerSource: 'vendor',
          headerEvidence: 'Use Token.',
          queryParam: null,
          scopes: [],
          variables: [],
          setupSteps: null,
          tokenLifetime: null,
          testUrl: null,
          scheme: {},
          variablesSchema: null,
          file: null,
        }),
      ),
    );
    renderApp('/apis/stripe/auth/api-key');
    const how = await screen.findByRole('region', { name: 'How it works' });
    expect(within(how).getByText('Authorization: Token <token>')).toBeInTheDocument();
  });

  it('an older server without the fields: the page is as before', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/stripe/auth/api-key`, () =>
        HttpResponse.json({
          api: 'stripe',
          build: 'b',
          id: 'api-key',
          docId: 'auth:api-key',
          name: 'API key',
          type: 'API_KEY',
          grantType: null,
          headerName: 'Authorization',
          queryParam: null,
          scopes: [],
          variables: [],
          setupSteps: null,
          tokenLifetime: null,
          testUrl: null,
          scheme: {},
          variablesSchema: null,
          file: null,
        }),
      ),
    );
    renderApp('/apis/stripe/auth/api-key');
    const how = await screen.findByRole('region', { name: 'How it works' });
    expect(within(how).getByText('Authorization')).toBeInTheDocument();
    expect(how.querySelector('blockquote')).toBeNull();
  });
});
