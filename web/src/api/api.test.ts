import { http, HttpResponse } from 'msw';
import { server, TEST_API_BASE } from '@/test/server';
import { apiBaseUrl, mocksEnabled } from './config';
import { createApiClient } from './client';
import { ApiError } from './types';

describe('apiBaseUrl', () => {
  it('reads the env value and trims trailing slashes', () => {
    expect(apiBaseUrl({ VITE_API_BASE_URL: 'http://x:1///' })).toBe('http://x:1');
  });
  it('throws when unset or blank: no hard-coded default', () => {
    expect(() => apiBaseUrl({})).toThrow(/VITE_API_BASE_URL/);
    expect(() => apiBaseUrl({ VITE_API_BASE_URL: '  ' })).toThrow(/VITE_API_BASE_URL/);
  });
  it('mocksEnabled only for the literal "true"', () => {
    expect(mocksEnabled({ VITE_USE_MOCKS: 'true' })).toBe(true);
    expect(mocksEnabled({ VITE_USE_MOCKS: '1' })).toBe(false);
    expect(mocksEnabled({})).toBe(false);
  });
});

describe('createApiClient', () => {
  const client = createApiClient(TEST_API_BASE);

  it('lists and fetches APIs', async () => {
    const list = await client.listApis();
    expect(list.items).toHaveLength(6);
    expect((await client.getApi('stripe')).name).toBe('Stripe API');
  });

  it('raises ApiError with the server detail', async () => {
    await expect(client.getApi('missing')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: 'API not found',
    });
    await expect(client.getApi('missing')).rejects.toBeInstanceOf(ApiError);
  });

  it('sends the maintainer key only when provided', async () => {
    let auth: string | null = 'unset';
    server.use(
      http.get(`${TEST_API_BASE}/v1/apis`, ({ request }) => {
        auth = request.headers.get('authorization');
        return HttpResponse.json({ items: [] });
      }),
    );
    await client.listApis();
    expect(auth).toBeNull();
    await createApiClient(TEST_API_BASE, { maintainerKey: () => 'k1' }).listApis();
    expect(auth).toBe('Bearer k1');
  });
});
