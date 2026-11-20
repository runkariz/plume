import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** A hit the server adds to an auth question: an app or auth document with no snippet and no ranks. */
for (const theme of THEMES) {
  test.describe(`search, added hit (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('no empty snippet box, no "null": the hit says it was added', async ({ page }) => {
      await page.goto('/apis/shopify/try');
      await page.getByLabel('Question or search text').fill('how do I sign a request');
      await page.getByRole('button', { name: 'Run' }).click();
      const hit = page
        .locator('.res')
        .filter({ has: page.getByRole('heading', { name: 'Shopify Admin REST' }) });
      await expect(hit).toContainText('Added to the results: it has no text or meaning rank.');
      await expect(hit).not.toContainText(/null|undefined|NaN/);
      await expect(hit.locator('p.muted')).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      const list = page.getByRole('list').filter({ has: hit });
      await shotOf(list.first(), 'w43-search-added-hit', theme);
    });
  });
}
