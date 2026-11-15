import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** At 375 px nothing may scroll sideways, and the pages still pass axe. */
const PAGES: { name: string; path: string; ready: (p: Page) => Promise<void> }[] = [
  {
    name: 'home',
    path: '/',
    ready: (p) => expect(p.getByRole('link', { name: 'Stripe API' })).toBeVisible(),
  },
  {
    name: 'api-detail',
    path: '/apis/shopify',
    ready: (p) => expect(p.getByRole('heading', { level: 1, name: /Shopify/ })).toBeVisible(),
  },
  {
    name: 'try-it',
    path: '/apis/shopify/try',
    ready: async (p) => {
      await p.getByRole('button', { name: 'Run' }).click();
      await expect(p.getByText('Query trace')).toBeVisible();
    },
  },
  {
    name: 'pick-apps',
    path: '/models',
    ready: (p) => expect(p.getByRole('checkbox', { name: /Shopify/ })).toBeVisible(),
  },
  {
    name: 'suggestions',
    path: '/models/suggest?apis=shopify,woocommerce,mirakl',
    ready: (p) => expect(p.getByRole('heading', { name: 'Inventory' })).toBeVisible(),
  },
  {
    name: 'endpoint-detail',
    path: '/apis/shopify/documents/endpoint%3Acreate-order',
    ready: (p) => expect(p.getByRole('region', { name: 'Request body' })).toBeVisible(),
  },
  {
    name: 'auth-scheme',
    path: '/apis/shopify/auth/oauth2-authorization-code',
    ready: (p) => expect(p.getByRole('region', { name: 'Scopes' })).toBeVisible(),
  },
  {
    name: 'triggers',
    path: '/apis/shopify?section=triggers',
    ready: (p) => expect(p.getByRole('region', { name: 'Webhook delivery' })).toBeVisible(),
  },
  {
    name: 'trigger-detail',
    path: '/apis/shopify/triggers/app%2Fscopes_update',
    ready: (p) => expect(p.getByLabel('Event JSON')).toBeVisible(),
  },
  {
    name: 'unlisted-model',
    path: '/models/u-3f9a0c71d2e84b5f9a6c1d7e8b2a4c60',
    ready: (p) => expect(p.getByRole('region', { name: 'Share this model' })).toBeVisible(),
  },
  {
    name: 'model-view-big-table',
    path: '/models/m-38f24111baf1076f44c9cfa7',
    ready: (p) => expect(p.getByRole('table')).toBeVisible(),
  },
  {
    name: 'model-view',
    path: '/models/snap_8f3a21',
    ready: (p) => expect(p.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible(),
  },
  {
    name: 'sign-in',
    path: '/maintainer',
    ready: (p) => expect(p.getByRole('button', { name: 'Sign in' })).toBeVisible(),
  },
];

for (const theme of THEMES) {
  test.describe(`375 px (${theme})`, () => {
    test.use({ theme, viewport: { width: 375, height: 800 } });

    for (const pg of PAGES) {
      test(`${pg.name}: no horizontal scroll, axe clean`, async ({ page }) => {
        await page.goto(pg.path);
        await pg.ready(page);
        await settle(page);
        const { scrollWidth, clientWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(scrollWidth, `${pg.name} scrolls sideways`).toBeLessThanOrEqual(clientWidth);
        await expectNoSeriousA11y(page);
        await shot(page, `w8-mobile-${pg.name}`, theme);
      });
    }

    test('the header is usable: the theme toggle and the links are reachable', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('link', { name: 'Models', exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: 'GitHub', exact: true })).toBeVisible(); // icon only, name kept for screen readers
      await page.getByRole('button', { name: /Switch to (dark|light) theme/ }).click();
      await expect(page.getByRole('link', { name: 'Maintainer' })).toBeVisible();
    });
  });
}
