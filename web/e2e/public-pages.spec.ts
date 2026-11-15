import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

for (const theme of THEMES) {
  test.describe(`public pages (${theme})`, () => {
    test.use({ theme });

    test('Home lists the APIs, filters by category, opens a detail page', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('link', { name: 'Shopify Admin REST' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'All · 6' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w2-01-home', theme);

      await page.getByRole('button', { name: 'Communication · 2' }).click();
      await expect(page.locator('article.api-card')).toHaveCount(2);
      await page.getByRole('button', { name: 'All · 6' }).click();
      await page.getByRole('link', { name: 'Shopify Admin REST' }).click();
      await expect(page).toHaveURL(/\/apis\/shopify$/);
    });

    test('API detail shows stats, browse, quality, index, connect', async ({ page }) => {
      await page.goto('/apis/shopify');
      await expect(
        page.getByRole('heading', { level: 1, name: 'Shopify Admin REST API' }),
      ).toBeVisible();
      await expect(page.getByText('/admin/api/latest/orders.json').first()).toBeVisible();
      await expect(page.getByText('0 / 40')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w2-02-api-detail', theme);

      await page.getByRole('radio', { name: 'Guides', exact: true }).check({ force: true });
      await expect(page.getByText('REST Admin API request rate limits')).toBeVisible();
    });

    test('Try it: search shows ranked results with the query trace', async ({ page }) => {
      await page.goto('/apis/shopify/try');
      await expect(page.getByText('Build 2026-11-14 · live')).toBeVisible();
      await page.getByRole('button', { name: 'Run' }).click();
      await expect(page.getByText('Query trace')).toBeVisible();
      await expect(
        page.getByText('Pagination: Link header, URL lifespan and range searches'),
      ).toBeVisible();
      await expect(page.getByText('What Claude receives')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w2-08-try-it', theme);

      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      await shot(page, 'w2-08-try-it-check', theme);
    });
  });
}

test('keyboard focus is visible on the primary controls', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Shopify Admin REST' })).toBeVisible();
  await page.keyboard.press('Tab');
  const outline = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const cs = getComputedStyle(el);
    return { width: cs.outlineWidth, style: cs.outlineStyle };
  });
  expect(outline.style).not.toBe('none');
  expect(outline.width).not.toBe('0px');
});
