import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Answer quality per question source: Docs and Spec rows under the combined scores. */
for (const theme of THEMES) {
  test.describe(`answer quality by source (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the API page shows docs and spec rows', async ({ page }) => {
      await page.goto('/apis/shopify');
      const table = page.getByRole('table', { name: 'By question source' });
      await expect(table.getByRole('row', { name: /Docs questions/ })).toContainText(
        '26 questions',
      );
      await expect(table.getByRole('row', { name: /Spec questions/ })).toContainText('0.91');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('heading', { name: 'Answer quality' }).locator('..'),
        'w29-quality-sources',
        theme,
      );
    });
  });
}

test('375 px: the quality card does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/apis/shopify');
  await expect(page.getByRole('table', { name: 'By question source' })).toBeVisible();
  const wide = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(wide).toBe(false);
});
