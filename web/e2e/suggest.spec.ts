import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** The suggestions page: reason, search, per-API filter, scope, paging, and the icons of the app pickers. */
const url = '/models/suggest?apis=shopify,woocommerce,mirakl';

for (const theme of THEMES) {
  test.describe(`suggestions (${theme})`, () => {
    test.use({ theme });

    test('reason under each concept, search and per-API filter in the URL', async ({ page }) => {
      await page.goto(`${url}&require=shopify,woocommerce`);
      const rows = page.locator('article.concept h3');
      await expect(rows.first()).toBeVisible();
      await expect(page.locator('.concept-reason').first()).toContainText(
        'is documented as a model',
      );
      await expect(page.getByText(/as documented by/)).toHaveCount(0);
      await page.getByRole('searchbox', { name: 'Search concepts' }).fill('dis');
      await expect(rows).toHaveText(['Discount']);
      await expect(page).toHaveURL(/q=dis/);
      await expect(page).toHaveURL(/require=shopify%2Cwoocommerce|require=shopify,woocommerce/);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-suggest-filtered', theme);
    });

    test('paging, and the concepts that exist in only one API', async ({ page }) => {
      await page.goto(url);
      await expect(page.locator('article.concept')).toHaveCount(24);
      await page.getByRole('button', { name: 'Next' }).click();
      await expect(page).toHaveURL(/page=2/);
      await expect(page.getByRole('button', { name: 'Next' })).toBeDisabled();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-suggest-page-2', theme);
      await page.getByRole('radio', { name: /^Only in one API/ }).click({ force: true });
      await expect(page.getByRole('heading', { name: 'Theme' })).toBeVisible();
      await expect(page).toHaveURL(/only=single/);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-suggest-single', theme);
    });

    test('the app pickers and the API chips carry the package icon', async ({ page }) => {
      await page.goto('/models');
      const icon = page.locator('.pick-card img').first();
      await expect(icon).toHaveAttribute('src', /\/v1\/apis\/shopify\/icon$/);
      await expect
        .poll(() => icon.evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0);
      expect((await icon.boundingBox())?.width ?? 0).toBeGreaterThan(20);
      await page.getByRole('checkbox', { name: /Shopify/ }).check({ force: true });
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-pick-apps-icons', theme);
    });
  });
}
