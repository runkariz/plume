import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { authDetailFor, environmentsFor } from '@/mocks/sectionData';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

const tiktokEnvs = () => ({
  ...environmentsFor('shopify'),
  environments: [
    {
      key: 'production',
      name: 'production',
      kind: 'production',
      baseUrl: 'https://open-api.tiktokglobalshop.com',
      isDefault: true,
      servers: {
        auth_2: 'https://auth.tiktok-shops.com',
        api: 'https://open-api.tiktokglobalshop.com',
        auth: 'https://services.tiktokshop.com',
        upload: 'https://up.example.com',
      },
    },
    {
      key: 'sandbox',
      name: 'sandbox',
      kind: 'sandbox',
      baseUrl: 'https://open-api-sandbox.tiktokglobalshop.com',
      servers: {
        api: 'https://open-api-sandbox.tiktokglobalshop.com',
        auth: 'https://services-sandbox.tiktokshop.com',
      },
    },
  ],
  notices: [],
});

describe('every server of an environment', () => {
  it('lists each server by role, the base URL first, unknown keys as written', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/environments`, () =>
        HttpResponse.json(tiktokEnvs()),
      ),
    );
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    const prod = within(card).getByRole('group', { name: 'Servers of production' });
    const rows = Array.from(prod.querySelectorAll('.env-server')).map((r) => r.textContent);
    expect(rows).toEqual([
      'APIhttps://open-api.tiktokglobalshop.com',
      'Auth 2https://auth.tiktok-shops.com',
      'Authhttps://services.tiktokshop.com',
      'uploadhttps://up.example.com',
    ]);
    const sandbox = within(card).getByRole('group', { name: 'Servers of sandbox' });
    expect(sandbox).toHaveTextContent('Authhttps://services-sandbox.tiktokshop.com');
  });

  it('shows a lone base URL as before when the environment names no servers', async () => {
    const e = environmentsFor('shopify');
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/environments`, () =>
        HttpResponse.json({
          ...e,
          environments: [{ key: 'p', name: 'p', baseUrl: 'https://only.example.com' }],
        }),
      ),
    );
    renderApp('/apis/shopify');
    const card = await screen.findByRole('region', { name: 'Environments' });
    expect(within(card).getByText('https://only.example.com')).toBeInTheDocument();
    expect(within(card).queryByRole('group')).not.toBeInTheDocument();
  });
});

describe('auth URLs resolved per environment', () => {
  const scheme = {
    authUrl: '{{app_env.servers.auth}}/open/authorize',
    accessTokenUrl: '{{app_env.servers.auth_2}}/api/v2/token/get',
    refreshTokenUrl: '{{app_env.servers.auth_3}}/api/v2/token/refresh',
    other: 'https://x',
  };
  function use() {
    const detail = authDetailFor('shopify', 'oauth2-authorization-code');
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/environments`, () =>
        HttpResponse.json(tiktokEnvs()),
      ),
      http.get(`${TEST_API_BASE}/v1/apis/shopify/auth/oauth2-authorization-code`, () =>
        HttpResponse.json({ ...detail, scheme }),
      ),
    );
  }

  it('shows each template with what it is in each environment', async () => {
    use();
    renderApp('/apis/shopify/auth/oauth2-authorization-code');
    const card = await screen.findByRole('region', { name: 'How it works' });
    expect(await within(card).findByText('{{app_env.servers.auth}}/open/authorize')).toBeVisible();
    const authorize = await within(card).findByRole('list', {
      name: 'Authorize URL per environment',
    });
    expect(authorize).toHaveTextContent(
      'production: https://services.tiktokshop.com/open/authorize',
    );
    expect(authorize).toHaveTextContent(
      'sandbox: https://services-sandbox.tiktokshop.com/open/authorize',
    );
    // auth_2 exists only in production: nothing is guessed for the sandbox
    const token = within(card).getByRole('list', {
      name: 'Token URL per environment',
    });
    expect(token.querySelectorAll('li')).toHaveLength(1);
    expect(token).toHaveTextContent('production: https://auth.tiktok-shops.com/api/v2/token/get');
    // a server no environment has: the template is shown alone
    expect(
      within(card).queryByRole('list', {
        name: 'Refresh URL per environment',
      }),
    ).not.toBeInTheDocument();
    expect(within(card).getByText('{{app_env.servers.auth_3}}/api/v2/token/refresh')).toBeVisible();
    // other fields of the scheme are not shown as URLs
    expect(within(card).queryByText('https://x')).not.toBeInTheDocument();
  });

  it('still shows the templates when the environments cannot be read', async () => {
    use();
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis/shopify/environments`, () =>
        HttpResponse.json({ detail: 'x' }, { status: 500 }),
      ),
    );
    renderApp('/apis/shopify/auth/oauth2-authorization-code');
    const card = await screen.findByRole('region', { name: 'How it works' });
    expect(await within(card).findByText('{{app_env.servers.auth}}/open/authorize')).toBeVisible();
    expect(within(card).queryByRole('list')).not.toBeInTheDocument();
  });
});
