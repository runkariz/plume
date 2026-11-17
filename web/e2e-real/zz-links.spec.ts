import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The links a package states, as the real API sends them: an endpoint's required scopes per auth scheme and its
 * guides, a guide's endpoints, a scope's endpoints. Needs a Shopify package whose knowledge units carry
 * endpointId/endpointIds and whose products endpoint has requiredScopes with an authId, and a WooCommerce copy whose
 * unit `authentication` has endpointId and a knowledge-export/unit-links.json page link: PLUME_E2E_LINKS=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const LINKS = process.env.PLUME_E2E_LINKS === 'true';
const PRODUCTS = 'endpoint:GET~/admin/api/{version}/products.json';
const CREATE = 'endpoint:POST~/admin/api/{version}/products.json';
const RATE = 'guide:rate-limit-admin-rest-rest-admin-api-request-rate-limits';
const doc = (id: string) => `/apis/shopify/documents/${encodeURIComponent(id)}`;

for (const theme of THEMES) {
  test.describe(`document links (${theme})`, () => {
    test.skip(!LINKS, 'set PLUME_E2E_LINKS=true with the linked Shopify package loaded');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('an endpoint shows the scopes per scheme (linked) and the guides that name it', async ({
      page,
      request,
    }) => {
      const body = (await (
        await request.get(`${API}/v1/apis/shopify/documents/${encodeURIComponent(PRODUCTS)}`)
      ).json()) as {
        requiredScopes: { authId: string; scopes: string[] }[];
        guides: string[];
      };
      expect(body.requiredScopes[0]?.authId).toBe('oauth2-authorization-code');
      await page.goto(doc(PRODUCTS));
      const scopes = page.getByRole('region', { name: 'Required scopes' });
      await expect(scopes).toContainText('read_products');
      await expect(scopes).toContainText('read_inventory');
      const guides = page.getByRole('region', { name: 'Related guides' });
      // a guide is shown by its own title, not its id
      await expect(guides.getByRole('link')).toHaveCount(body.guides.length);
      await expect(guides.getByRole('link').first()).not.toContainText('guide:');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w28-real-endpoint-links', theme);
      await scopes.getByRole('link', { name: 'oauth2-authorization-code' }).click();
      await expect(page).toHaveURL(/\/auth\/oauth2-authorization-code$/);
    });

    test('a guide lists its endpoints (the unknown one is not shown)', async ({ page }) => {
      await page.goto(doc(RATE));
      const card = page.getByRole('region', { name: 'About these endpoints' });
      await expect(card.getByRole('link')).toHaveCount(2);
      await expect(card).toContainText('/admin/api/{version}/products.json');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w28-real-guide-endpoints', theme);
      await card.getByRole('link').first().click();
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page).toHaveURL(
        new RegExp(encodeURIComponent(CREATE).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
      );
    });

    test('a guide says why each endpoint is linked (text, then page)', async ({
      page,
      request,
    }) => {
      // WooCommerce copy with a unit that names an endpoint and a unit-links.json page link for the same unit
      const body = (await (
        await request.get(
          `${API}/v1/apis/woocommerce/documents/${encodeURIComponent('guide:authentication')}`,
        )
      ).json()) as { endpointLinks: { linkBasis: string }[] };
      expect(body.endpointLinks.map((l) => l.linkBasis)).toEqual(['text', 'page']);
      await page.goto(`/apis/woocommerce/documents/${encodeURIComponent('guide:authentication')}`);
      const card = page.getByRole('region', { name: 'About these endpoints' });
      await expect(card.getByRole('link')).toHaveCount(2);
      await expect(card).toContainText('names it');
      await expect(card).toContainText('same docs page');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w30-real-link-basis', theme);
    });

    test('the auth scheme shows the endpoints of the scopes that name them', async ({ page }) => {
      await page.goto('/apis/shopify/auth/oauth2-authorization-code');
      const scopes = page.getByRole('region', { name: 'Scopes' });
      const read = scopes.getByRole('list', { name: 'Endpoints that need read_products' });
      await expect(read.getByRole('link')).toHaveCount(1);
      await expect(
        scopes.getByRole('list', { name: 'Endpoints that need read_inventory' }),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(scopes, 'w28-real-scheme-scopes', theme);
      await read.getByRole('link').click();
      await expect(page.getByRole('region', { name: 'Required scopes' })).toBeVisible();
    });
  });
}
