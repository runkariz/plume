import { expect, type APIRequestContext } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * The package sections on the real API (feature/package-sections): Auth, Triggers / Webhooks, Environments and the
 * package icon, with the fixtures shopify-mini (OAuth2 + scopes, trigger events, icon), woo-mini (three auth
 * schemes, no triggers, icon) and test-catalog (no icon). Everything is read from the API first, so the specs
 * follow the data instead of hard-coded ids.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
/** What the BROWSER calls: the API's address, or (PLUME_E2E_SAME_ORIGIN=true: web built with an empty base URL, /v1 proxied) a relative path. */
const FROM_BROWSER = process.env.PLUME_E2E_SAME_ORIGIN === 'true' ? '' : API;

const json = async <T>(request: APIRequestContext, path: string): Promise<T> =>
  (await (await request.get(`${API}${path}`)).json()) as T;

interface AuthList {
  present: boolean;
  schemes: { id: string; name: string; scopes: number; variables: number }[];
}
interface TriggerList {
  present: boolean;
  note: string | null;
  total: number;
  items: { key: string; title: string }[];
}

test('the sections answer on the real API', async ({ request }) => {
  const shopify = await json<{
    sections: { auth: number; triggers: number };
    logo: { url: string | null };
  }>(request, '/v1/apis/shopify');
  expect(shopify.sections.auth).toBeGreaterThan(0);
  expect(shopify.sections.triggers).toBeGreaterThan(0);
  expect(shopify.logo.url).toBe('/v1/apis/shopify/icon'); // relative: never an external URL
  const icon = await request.get(`${API}/v1/apis/shopify/icon`);
  expect(icon.status()).toBe(200);
  expect(icon.headers()['content-type']).toMatch(/^image\//);
  expect(icon.headers()['x-content-type-options']).toBe('nosniff');
  const none = await json<{ logo: { url: string | null } }>(request, '/v1/apis/test-catalog-api');
  expect(none.logo.url).toBeNull();
});

for (const theme of THEMES) {
  test.describe(`package sections on the real API (${theme})`, () => {
    test.use({ theme });

    test('icon on the card and the header, letter tile when the package has none', async ({
      page,
    }) => {
      await page.goto('/');
      const shopify = page.locator('article.api-card', { hasText: /shopify/i }).first();
      await expect(shopify.locator('img')).toHaveAttribute(
        'src',
        `${FROM_BROWSER}/v1/apis/shopify/icon`,
      );
      await expect
        .poll(() => shopify.locator('img').evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0);
      const catalog = page.locator('article.api-card', { hasText: 'Test Catalog API' });
      await expect(catalog.locator('img')).toHaveCount(0);
      await expect(catalog.locator('.logo')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-home-icons', theme);
      await shopify.getByRole('link').click();
      await expect(page.locator('.title-left img')).toHaveAttribute(
        'src',
        `${FROM_BROWSER}/v1/apis/shopify/icon`,
      );
      await expect(page.getByRole('region', { name: 'Environments' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-api-header', theme);
    });

    test('Auth: the real schemes, their scopes and variables', async ({ page, request }) => {
      const list = await json<AuthList>(request, '/v1/apis/shopify/auth');
      const scheme = list.schemes[0];
      expect(scheme, 'shopify-mini has an auth scheme').toBeTruthy();
      await page.goto('/apis/shopify?section=auth');
      const card = page.getByRole('region', { name: 'Authentication' });
      await expect(card.getByRole('link', { name: scheme?.name ?? '' })).toBeVisible();
      await expect(card.getByText(`${scheme?.scopes} scopes`)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-auth-list', theme);
      await card.getByRole('link', { name: scheme?.name ?? '' }).click();
      await expect(page.getByRole('heading', { level: 1, name: scheme?.name ?? '' })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Scopes' })).toContainText(
        `(${scheme?.scopes})`,
      );
      await expect(page.getByRole('searchbox', { name: 'Filter scopes' })).toBeVisible(); // more than 12
      // identifiers are shown as the package spells them (never uppercased by a table style)
      await expect(page.getByRole('rowheader').first()).toHaveCSS('text-transform', 'none');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-auth-scheme', theme);

      // a package with several schemes and variables (woo-mini)
      const woo = await json<AuthList>(request, '/v1/apis/woocommerce/auth');
      expect(woo.schemes.length).toBeGreaterThanOrEqual(2);
      await page.goto('/apis/woocommerce?section=auth');
      for (const s of woo.schemes)
        await expect(
          page.getByRole('region', { name: 'Authentication' }).getByRole('link', { name: s.name }),
        ).toBeVisible();
      const withVars = woo.schemes.find((s) => s.variables > 0);
      if (withVars) {
        await page.getByRole('link', { name: withVars.name }).click();
        await expect(page.getByRole('region', { name: 'Variables' })).toContainText('required');
        await shot(page, 'w11-real-auth-variables', theme);
      }
    });

    test('Triggers: the real events, an event page, and "Not in this package" for woo-mini', async ({
      page,
      request,
    }) => {
      const t = await json<TriggerList>(request, '/v1/apis/shopify/triggers');
      expect(t.present).toBe(true);
      const first = t.items[0];
      await page.goto('/apis/shopify?section=triggers');
      const card = page.getByRole('region', { name: 'Triggers and webhooks' });
      await expect(card.getByRole('link', { name: first?.title ?? '' })).toBeVisible();
      await expect(card.getByText(new RegExp(`${t.total} of ${t.total} events`))).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-triggers-list', theme);
      await card.getByRole('link', { name: first?.title ?? '' }).click();
      await expect(page).toHaveURL(new RegExp(encodeURIComponent(first?.key ?? '')));
      await expect(page.getByRole('heading', { level: 1, name: first?.title ?? '' })).toBeVisible();
      await expect(page.getByLabel('Event JSON')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-trigger-detail', theme);

      // the webhook mechanism: stream endpoint ids resolve to METHOD + path linked to the endpoint page when the
      // build has the endpoint (shopify-mini has the subscribe endpoint), and stay marked raw ids when it does not
      const refs = (
        await json<{
          endpointRefs: Record<string, { docId: string; method: string; path: string } | null>;
        }>(request, '/v1/apis/shopify/triggers')
      ).endpointRefs;
      const resolved = Object.entries(refs).filter(([, v]) => v);
      const missing = Object.entries(refs).filter(([, v]) => !v);
      expect(resolved.length, 'shopify-mini resolves its subscribe endpoint').toBeGreaterThan(0);
      await page.goto('/apis/shopify?section=triggers');
      const mech = page.getByRole('region', { name: 'Webhook delivery' });
      for (const [, ref] of resolved)
        await expect(mech.getByRole('link', { name: ref?.path ?? '' }).first()).toHaveAttribute(
          'href',
          `/apis/shopify/documents/${encodeURIComponent(ref?.docId ?? '')}`,
        );
      if (missing.length) await expect(mech.getByText('(not in this build)').first()).toBeVisible();
      await shot(page, 'w12-real-webhook-endpoints', theme);

      const woo = await json<TriggerList>(request, '/v1/apis/woocommerce/triggers');
      expect(woo.present).toBe(false);
      await page.goto('/apis/woocommerce?section=triggers');
      await expect(page.getByRole('heading', { name: 'Not in this package' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-real-triggers-empty', theme);
    });
  });
}
