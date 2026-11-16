import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * What a real package says about an API, shown as the server sends it: rate limits (a limit per operation in
 * Amazon's), the vendor's real paths, and field constraints. WooCommerce (fixtures) has real paths; the Amazon
 * checks need the real Amazon package loaded as `amazon-sp-vendor`: PLUME_E2E_AMAZON=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const AMAZON = process.env.PLUME_E2E_AMAZON === 'true';

interface Item {
  id: string;
  path?: string;
  realPath?: string | null;
}

for (const theme of THEMES) {
  test.describe(`real paths, rate limits, constraints (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('WooCommerce Browse shows the real path; Shopify keeps its own', async ({
      page,
      request,
    }) => {
      const woo = (await (
        await request.get(`${API}/v1/apis/woocommerce/items?kind=endpoint&limit=9`)
      ).json()) as {
        items: Item[];
      };
      const withReal = woo.items.filter((i) => i.realPath);
      expect(withReal.length).toBeGreaterThan(0);
      await page.goto('/apis/woocommerce');
      const first = withReal[0] as Item;
      await expect(
        page.getByRole('link', { name: first.realPath as string }).first(),
      ).toBeVisible();
      // the template path ("{version}") is not what the list shows
      await expect(page.getByRole('link', { name: first.path as string, exact: true })).toHaveCount(
        0,
      );
      await settle(page);
      await shotOf(page.locator('.browse'), 'w27-real-woo-browse', theme);
      // Shopify: null realPath, its own path
      const shop = (await (
        await request.get(`${API}/v1/apis/shopify/items?kind=endpoint&limit=1`)
      ).json()) as {
        items: Item[];
      };
      expect(shop.items[0]?.realPath ?? null).toBeNull();
      await page.goto('/apis/shopify');
      await expect(
        page.getByRole('link', { name: (shop.items[0] as Item).path as string }).first(),
      ).toBeVisible();
    });

    test.describe('Amazon', () => {
      test.skip(!AMAZON, 'needs the real Amazon package: PLUME_E2E_AMAZON=true');

      test('the API page lists the rate limits the server sends, the first rows and the rest on request', async ({
        page,
        request,
      }) => {
        const d = (await (await request.get(`${API}/v1/apis/amazon-sp-vendor`)).json()) as {
          rateLimits: { group?: string; limit?: number; windowSeconds?: number }[];
        };
        expect(d.rateLimits.length).toBeGreaterThan(8);
        await page.goto('/apis/amazon-sp-vendor');
        const card = page.getByRole('region', { name: 'Rate limits' });
        await expect(card).toContainText(`Rate limits (${d.rateLimits.length})`);
        const first = d.rateLimits[0];
        await expect(card.getByText(first?.group ?? '', { exact: true })).toBeVisible();
        await expect(card.getByRole('row')).toHaveCount(1 + 8);
        await card.getByRole('button', { name: `Show all ${d.rateLimits.length}` }).click();
        await expect(card.getByRole('row')).toHaveCount(1 + d.rateLimits.length);
        await expect(card.getByText('x-amzn-RateLimit-Limit')).toHaveCount(1);
        await settle(page);
        await expectNoSeriousA11y(page);
        await shotOf(card, 'w27-real-amazon-rate-limits', theme);
      });

      test('Browse shows the real path of an Amazon operation', async ({ page, request }) => {
        const r = (await (
          await request.get(`${API}/v1/apis/amazon-sp-vendor/items?kind=endpoint&limit=9`)
        ).json()) as {
          items: Item[];
        };
        const first = r.items.find((i) => i.realPath && i.realPath !== i.path) as Item;
        expect(first, 'an operation whose real path differs from its template').toBeTruthy();
        await page.goto('/apis/amazon-sp-vendor');
        await expect(
          page.getByRole('link', { name: first.realPath as string }).first(),
        ).toBeVisible();
        await settle(page);
        await shotOf(page.locator('.browse'), 'w27-real-amazon-browse', theme);
      });

      test('an endpoint page: the real path, its rate limit and the constraints of its fields', async ({
        page,
        request,
      }) => {
        const r = (await (
          await request.get(`${API}/v1/apis/amazon-sp-vendor/items?kind=endpoint&limit=9`)
        ).json()) as {
          items: Item[];
        };
        const id = (r.items.find((i) => i.realPath) as Item).id;
        const doc = (await (
          await request.get(`${API}/v1/apis/amazon-sp-vendor/documents/${encodeURIComponent(id)}`)
        ).json()) as {
          realPath: string;
          rateLimit: { bucket: string; cost: number; group: { group: string } | null } | null;
          fields: { name: string; constraints: Record<string, unknown> | null }[];
        };
        await page.goto(`/apis/amazon-sp-vendor/documents/${encodeURIComponent(id)}`);
        await expect(page.getByText(doc.realPath, { exact: true })).toBeVisible();
        if (doc.rateLimit) {
          const card = page.getByRole('region', { name: 'Rate limit' });
          await expect(card).toContainText(doc.rateLimit.bucket);
          if (doc.rateLimit.group?.group)
            await expect(card).toContainText(doc.rateLimit.group.group);
        }
        const constrained = doc.fields.find((f) => f.constraints);
        if (constrained) await expect(page.getByLabel('Constraints').first()).toBeVisible();
        await settle(page);
        await expectNoSeriousA11y(page);
        await shotOf(page.locator('main'), 'w27-real-amazon-endpoint', theme);
      });
    });
  });
}
