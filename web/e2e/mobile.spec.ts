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
      await expect(page.getByRole('link', { name: 'GitHub' })).toBeVisible(); // icon only, name kept for screen readers
      await page.getByRole('button', { name: /Switch to (dark|light) theme/ }).click();
      await expect(page.getByRole('link', { name: 'Maintainer' })).toBeVisible();
    });
  });
}
