import { http, HttpResponse } from 'msw';
import { server, TEST_API_BASE } from '@/test/server';
import { apiBaseUrl, mocksEnabled } from './config';
import { createApiClient } from './client';
import { ApiError } from './types';

describe('apiBaseUrl', () => {
  it('reads the env value and trims trailing slashes', () => {
    expect(apiBaseUrl({ VITE_API_BASE_URL: 'http://x:1///' })).toBe('http://x:1');
  });
  it('throws when unset: no hard-coded default', () => {
    expect(() => apiBaseUrl({})).toThrow(/VITE_API_BASE_URL/);
    expect(() => apiBaseUrl({ VITE_API_BASE_URL: 5 })).toThrow(/VITE_API_BASE_URL/);
  });
  it('an empty value or "/" means the same origin: relative calls', () => {
    for (const same of ['', '  ', '/', ' / ', '//'])
      expect(apiBaseUrl({ VITE_API_BASE_URL: same })).toBe('');
  });
  it('mocksEnabled only for the literal "true"', () => {
    expect(mocksEnabled({ VITE_USE_MOCKS: 'true' })).toBe(true);
    expect(mocksEnabled({ VITE_USE_MOCKS: '1' })).toBe(false);
    expect(mocksEnabled({})).toBe(false);
  });
});

describe('the same origin (an empty base URL)', () => {
  it('calls relative /v1 paths, JSON and event streams alike', async () => {
    const urls: string[] = [];
    const fetchImpl = ((url: string) => {
      urls.push(url);
      const sse = url.includes('/events');
      return Promise.resolve(
        new Response(
          sse
            ? 'id: 1\nevent: done\ndata: {"status":"succeeded","snapshotId":null}\n\n'
            : JSON.stringify({ items: [] }),
          { headers: { 'Content-Type': sse ? 'text/event-stream' : 'application/json' } },
        ),
      );
    }) as unknown as typeof fetch;
    const client = createApiClient('', { fetchImpl });
    expect(client.baseUrl).toBe('');
    await client.listApis();
    await client.watchModelJob('mj-1', () => undefined);
    expect(urls[0]).toBe('/v1/apis');
    expect(urls[1]).toBe('/v1/models/jobs/mj-1/events');
  });
});

describe('error bodies and dump download', () => {
  const jsonFetch = (status: number, body: unknown, headers: Record<string, string> = {}) =>
    (() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json', ...headers },
        }),
      )) as unknown as typeof fetch;

  it('reads {error, message}, FastAPI {detail:[{msg}]} and {detail: string}', async () => {
    await expect(
      createApiClient('http://x', {
        fetchImpl: jsonFetch(404, { error: 'not_found', message: 'No such API' }),
      }).getApi('a'),
    ).rejects.toMatchObject({ status: 404, message: 'No such API' });
    await expect(
      createApiClient('http://x', {
        fetchImpl: jsonFetch(422, { detail: [{ msg: 'field required' }] }),
      }).getApi('a'),
    ).rejects.toMatchObject({ status: 422, message: 'field required' });
    await expect(
      createApiClient('http://x', { fetchImpl: jsonFetch(409, { detail: 'wrong state' }) }).getApi(
        'a',
      ),
    ).rejects.toMatchObject({ message: 'wrong state' });
  });

  it('adds Retry-After to a 429 message', async () => {
    const c = createApiClient('http://x', {
      fetchImpl: jsonFetch(
        429,
        { error: 'rate_limited', message: 'Slow down.' },
        { 'Retry-After': '12' },
      ),
    });
    await expect(c.listApis()).rejects.toMatchObject({
      status: 429,
      message: 'Slow down. Try again in 12 s.',
    });
  });

  it('takes the dump file name from Content-Disposition', async () => {
    const f = (() =>
      Promise.resolve(
        new Response('x', {
          headers: { 'Content-Disposition': 'attachment; filename="shopify-b-123.dump.gz"' },
        }),
      )) as unknown as typeof fetch;
    const out = await createApiClient('http://x', { fetchImpl: f }).downloadDump('job-1');
    expect(out.filename).toBe('shopify-b-123.dump.gz');
    expect(out.blob.size).toBe(1);
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
