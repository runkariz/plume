import { expect, type APIRequestContext } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * Runs against the real Plume API (compose stack) loaded with the fixture packages
 * shopify-mini, test-catalog and second-catalog (`plume load tests/fixtures/packages/<name>`).
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
/** Where the browser's API calls must go: the API's address, or (PLUME_E2E_SAME_ORIGIN=true) the web's own origin. */
const CALLS_GO_TO =
  process.env.PLUME_E2E_SAME_ORIGIN === 'true'
    ? (process.env.PLUME_E2E_BASE_URL ?? 'http://127.0.0.1:18473')
    : API;

async function firstEndpoint(request: APIRequestContext, api: string) {
  const res = await request.get(`${API}/v1/apis/${api}/items?kind=endpoint&limit=5`);
  expect(res.ok()).toBe(true);
  const body = (await res.json()) as { items: { method: string; path: string; title: string }[] };
  const first = body.items[0];
  expect(first, 'the fixture has at least one endpoint').toBeTruthy();
  return first as { method: string; path: string; title: string };
}

test.describe('real API: contract', () => {
  test('health, CORS for the web origin and the error body', async ({ request }) => {
    const health = await request.get(`${API}/health`);
    expect(await health.json()).toMatchObject({ status: 'ok' });
    const pre = await request.fetch(`${API}/v1/apis`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'http://127.0.0.1:18473',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
      },
    });
    expect(pre.headers()['access-control-allow-origin']).toBe('http://127.0.0.1:18473');
    const missing = await request.get(`${API}/v1/apis/nope`);
    expect(missing.status()).toBe(404);
    expect(await missing.json()).toMatchObject({
      error: expect.any(String),
      message: expect.any(String),
    });
  });
});

for (const theme of THEMES) {
  test.describe(`real API: public pages (${theme})`, () => {
    test.use({ theme });

    test('Home lists the loaded APIs with real counts and honest quality state', async ({
      page,
      request,
    }) => {
      const list = (await (await request.get(`${API}/v1/apis`)).json()) as {
        items: { id: string; status: { recallAt5: number | null } }[];
      };
      await page.goto('/');
      await expect(page.getByRole('link', { name: 'Test Catalog API' })).toBeVisible();
      const count = list.items.length; // every loaded fixture: the API says how many
      await expect(page.locator('article.api-card')).toHaveCount(count);
      await expect(page.getByRole('button', { name: `All · ${count}` })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await expect(page.getByRole('button', { name: /^E-commerce · \d+$/ })).toBeVisible();
      // the chips show exactly what the API reports: a recall number only for evaluated builds
      const evaluated = list.items.filter((a) => a.status.recallAt5 !== null);
      await expect(page.getByText(/^Recall@5 \d/)).toHaveCount(evaluated.length);
      await expect(page.getByText('Not evaluated')).toHaveCount(
        list.items.length - evaluated.length,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w5-real-home', theme);
      await page.getByRole('searchbox', { name: 'Search APIs' }).fill('second');
      await expect(page.locator('article.api-card')).toHaveCount(1);
    });

    test('API detail shows real stats, browse, index and connect; quality is not faked', async ({
      page,
      request,
    }) => {
      const detail = (await (await request.get(`${API}/v1/apis/shopify`)).json()) as {
        name: string;
        endpoints: number;
        chunks: number;
        quality: {
          recallAt5: number;
          goldQuestions: number;
          inventedEndpoints: number | null;
          top1Rate?: number;
        } | null;
      };
      await page.goto('/apis/shopify');
      await expect(page.getByRole('heading', { level: 1, name: detail.name })).toBeVisible();
      await expect(page.getByText(String(detail.chunks), { exact: true })).toBeVisible();
      if (detail.quality) {
        await expect(
          page.getByText(`Gold set of ${detail.quality.goldQuestions} questions`),
        ).toBeVisible();
        await expect(
          page.getByText(detail.quality.recallAt5.toFixed(2), { exact: true }).first(),
        ).toBeVisible();
        await expect(page.getByText('null')).toHaveCount(0);
        if (detail.quality.inventedEndpoints === null)
          await expect(page.getByText('Invented endpoints')).toHaveCount(0);
        if (detail.quality.top1Rate !== undefined)
          await expect(page.getByText('Top-1 hit rate').first()).toBeVisible();
      } else {
        await expect(page.getByText('Not evaluated yet.')).toBeVisible();
      }
      await expect(page.getByText(/claude mcp add/)).toBeVisible();
      const ep = await firstEndpoint(request, 'shopify');
      await expect(page.getByText(ep.path).first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w5-real-api-detail', theme);

      await page.getByRole('searchbox', { name: /Filter by path/ }).fill(ep.path.slice(1, 12));
      await expect(page.getByText(ep.path).first()).toBeVisible();
      await page.getByRole('radio', { name: 'Models', exact: true }).check({ force: true });
      await expect(page.locator('.kind-tag').first()).toHaveText('model');
    });

    test('Try it: search with the real query trace, ask, check call', async ({ page, request }) => {
      await page.goto('/apis/shopify/try');
      await expect(page.getByText(/^Build b-/)).toBeVisible();
      await page
        .getByRole('textbox', { name: 'Question or search text' })
        .fill('fulfillment orders');
      await page.getByRole('button', { name: 'Run' }).click();
      await expect(page.getByText('Query trace')).toBeVisible();
      await expect(page.locator('.results li').first()).toBeVisible();
      await expect(page.getByText('Embedder', { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Postgres', { exact: true }).first()).toBeVisible();
      await expect(page.getByText('What Claude receives')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w5-real-try-it', theme);

      await page.getByRole('radio', { name: 'Ask' }).check({ force: true });
      await page.getByRole('button', { name: 'Ask', exact: true }).click();
      await expect(page.locator('.results li').first()).toBeVisible();

      const ep = await firstEndpoint(request, 'shopify');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption(ep.method);
      await page.getByLabel('Path').fill(ep.path);
      await page.getByLabel(/Parameters/).fill('');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      await shot(page, 'w5-real-try-it-check', theme);

      await page.getByLabel('Path').fill('/admin/api/latest/definitely_not_real.json');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText(/Not documented in build b-/)).toBeVisible();
    });
  });
}

test('an unknown API shows the real 404 message', async ({ page }) => {
  await page.goto('/apis/does-not-exist');
  await expect(page.getByRole('alert')).toContainText(/not found|unknown/i);
});

test('the browser never calls a mock: requests go to the real API', async ({ page }) => {
  const calls: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/v1/')) calls.push(r.url());
  });
  await page.goto('/');
  await expect(page.locator('article.api-card').first()).toBeVisible();
  expect(calls.length).toBeGreaterThan(0);
  expect(calls.every((u) => u.startsWith(`${CALLS_GO_TO}/v1/`))).toBe(true);
  expect(await page.evaluate(() => navigator.serviceWorker?.controller ?? null)).toBeNull();
});
