import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Links a package states: the scopes an endpoint needs per auth scheme, its guides, a guide's endpoints. */
const EP = encodeURIComponent('endpoint:GET~/orders.json');
const GUIDE = encodeURIComponent('guide:pagination');

for (const theme of THEMES) {
  test.describe(`document links (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('an endpoint shows its scopes per scheme and its guides', async ({ page }) => {
      await page.goto(`/apis/shopify/documents/${EP}`);
      const scopes = page.getByRole('region', { name: 'Required scopes' });
      await expect(scopes).toContainText('read_orders');
      const guides = page.getByRole('region', { name: 'Related guides' });
      await expect(guides.getByRole('link', { name: /Pagination/ })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w28-endpoint-links', theme);
      await scopes.getByRole('link', { name: 'oauth2-authorization-code' }).click();
      await expect(page).toHaveURL(/\/apis\/shopify\/auth\/oauth2-authorization-code$/);
    });

    test('a guide lists the endpoints it is about', async ({ page }) => {
      await page.goto(`/apis/shopify/documents/${GUIDE}`);
      const card = page.getByRole('region', { name: 'About these endpoints' });
      await expect(card.getByRole('link')).toHaveCount(3);
      await expect(card).toContainText('same docs page');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w28-guide-endpoints', theme);
      await card.getByRole('link').first().click();
      await expect(page.getByRole('region', { name: 'Required scopes' })).toBeVisible();
    });

    test('the auth scheme shows the endpoints of each scope, long lists collapsed', async ({
      page,
    }) => {
      await page.goto('/apis/shopify/auth/oauth2-authorization-code');
      const scopes = page.getByRole('region', { name: 'Scopes' });
      const read = scopes.getByRole('list', { name: 'Endpoints that need read_orders' });
      await expect(read.getByRole('link')).toHaveCount(3);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(scopes, 'w28-scheme-collapsed', theme);
      await scopes.getByRole('button', { name: 'Show all 5' }).click();
      await expect(read.getByRole('link')).toHaveCount(5);
      await shotOf(scopes, 'w28-scheme-open', theme);
    });
  });
}

test('375 px: the linked pages do not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  for (const url of [
    `/apis/shopify/documents/${EP}`,
    `/apis/shopify/documents/${GUIDE}`,
    '/apis/shopify/auth/oauth2-authorization-code',
  ]) {
    await page.goto(url);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await settle(page);
    const wide = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(wide, url).toBe(false);
  }
});
