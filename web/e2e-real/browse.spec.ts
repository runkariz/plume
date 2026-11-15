import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/** Browse on the real API: every item opens its detail page (endpoint, model, guide) with what the package holds. */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';

for (const theme of THEMES) {
  test.describe(`browse and detail on the real API (${theme})`, () => {
    test.use({ theme });

    test('an endpoint opens its detail: method, path, grouped parameters, request and response fields', async ({
      page,
      request,
    }) => {
      const list = (await (
        await request.get(`${API}/v1/apis/shopify/items?kind=endpoint&limit=50`)
      ).json()) as {
        items: { id: string; method: string; path: string; title: string }[];
      };
      const post = list.items.find((i) => i.method === 'POST');
      expect(post, 'the fixture has a POST endpoint').toBeTruthy();
      const detail = (await (
        await request.get(`${API}/v1/apis/shopify/documents/${encodeURIComponent(post?.id ?? '')}`)
      ).json()) as { fields: { location: string }[] };
      const locations = new Set(detail.fields.map((f) => f.location));

      await page.goto('/apis/shopify');
      await expect(page.locator('.ep-link').first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-browse', theme);

      // the exact item, found by the link target built from the id the API returned (ids carry the API version)
      await page.getByRole('searchbox', { name: /Filter by path/ }).fill(post?.path ?? '');
      await page
        .locator(`a.ep-link[href="/apis/shopify/documents/${encodeURIComponent(post?.id ?? '')}"]`)
        .click();
      await expect(page).toHaveURL(/\/apis\/shopify\/documents\//);
      await expect(page.getByRole('heading', { level: 1, name: post?.title ?? '' })).toBeVisible();
      await expect(page.getByText(post?.method ?? '', { exact: true }).first()).toBeVisible();
      const names: Record<string, string> = {
        path: 'Path parameters',
        query: 'Query parameters',
        header: 'Headers',
        body: 'Request body',
        response: 'Response fields',
      };
      for (const [loc, title] of Object.entries(names))
        await expect(page.getByRole('region', { name: title })).toHaveCount(
          locations.has(loc) ? 1 : 0,
        );
      await expect(page.getByRole('link', { name: 'Open the vendor page' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-endpoint-detail', theme);
      await page.getByRole('link', { name: /^Back to / }).click();
      await expect(page).toHaveURL(/\/apis\/shopify$/);
    });

    test('a model and a guide open their detail too', async ({ page }) => {
      await page.goto('/apis/shopify');
      await page.getByRole('radio', { name: 'Models', exact: true }).check({ force: true });
      const model = page.locator('.ep-link').first();
      await expect(model).toBeVisible();
      const title = (await model.textContent()) ?? '';
      await model.click();
      await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Fields' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-model-detail', theme);

      await page.goto('/apis/shopify');
      await page.getByRole('radio', { name: 'Guides', exact: true }).check({ force: true });
      const guide = page.locator('.ep-link').first();
      await expect(guide).toBeVisible();
      const gtitle = (await guide.textContent()) ?? '';
      await guide.click();
      await expect(page.getByRole('heading', { level: 1, name: gtitle })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Text' })).toBeVisible();
      await shot(page, 'w11-guide-detail', theme);
    });
  });
}
