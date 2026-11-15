import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** The docs of a model's APIs changed after it was built: the page says so and Regenerate opens a new session. */
for (const theme of THEMES) {
  test.describe(`stale model (${theme})`, () => {
    test.use({ theme });

    test('chip, banner with the builds, Regenerate opens a generation session', async ({
      page,
    }) => {
      await page.goto('/models/m-38f24111baf1076f44c9cfa7');
      await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible();
      await expect(
        page.getByText('Stale: built on older docs of Shopify, WooCommerce'),
      ).toBeVisible();
      await expect(page.getByText('This model is built on older docs')).toBeVisible();
      await expect(page.getByText('b-e9f58eb5a9cb')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w10-stale-model', theme);

      await page.getByRole('link', { name: 'Regenerate' }).click();
      const panel = page.getByRole('region', { name: 'Generation session' });
      await expect(
        panel.getByRole('heading', { name: 'Waiting for a draft: Order' }),
      ).toBeVisible();
      await expect(panel.getByLabel('Prompt for Claude')).toContainText('get_model_context(');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w10-regenerate-session', theme);
    });

    test('the models page lists models with their stale mark', async ({ page }) => {
      await page.goto('/models');
      const list = page.getByRole('region', { name: 'Official models' });
      await expect(list.getByRole('link', { name: 'Order' })).toBeVisible();
      await expect(list.getByText('Stale')).toBeVisible();
      await expect(list.getByText('Official').first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w10-model-list', theme);
    });
  });
}

test('a current model shows no stale mark', async ({ page }) => {
  await page.goto('/models/snap_8f3a21');
  await expect(page.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible();
  await expect(page.getByText(/Stale/)).toHaveCount(0);
});
