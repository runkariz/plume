import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

for (const theme of THEMES) {
  test.describe(`canonical models (${theme})`, () => {
    test.use({ theme });

    test('pick apps → suggested models → mapping view', async ({ page }) => {
      // 1 pick
      await page.goto('/models');
      await expect(page.getByRole('checkbox', { name: /Shopify Admin REST/ })).toBeVisible();
      for (const name of [/Shopify Admin REST/, /WooCommerce REST/, /Mirakl Seller API/])
        await page.getByRole('checkbox', { name }).check({ force: true });
      await expect(page.getByText('3 selected')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-09-pick-apps', theme);

      // 2 suggestions
      await page.getByRole('button', { name: 'Suggest models →' }).click();
      await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-10-suggested-models', theme);

      // 3 generate → mapping view with the stored snapshot's nodes and edges
      await page.getByRole('button', { name: 'Generate Inventory' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible();
      await expect(page.locator('.react-flow__node')).toHaveCount(7 + 14 + 3); // canonical + api fields + groups
      await expect(page.locator('.react-flow__edge')).toHaveCount(14);
      await expect(page.locator('.react-flow__edge.selected')).toHaveCount(1);
      await expect(
        page.getByRole('heading', { name: 'quantity_available ← Shopify' }),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-11-model-mapping-view', theme);

      // clicking an edge selects that mapping
      await page
        .locator('.react-flow__edge[aria-label="manage_stock from Shopify (derived)"]')
        .click({ force: true });
      await expect(page.getByRole('heading', { name: 'manage_stock ← Shopify' })).toBeVisible();
      await expect(page.getByText('derived: not null = true')).toBeVisible();
    });
  });
}

test('suggestions need two APIs', async ({ page }) => {
  await page.goto('/models/suggest?apis=shopify');
  await expect(page.getByText('Pick at least two APIs')).toBeVisible();
});

test('a missing model shows not found', async ({ page }) => {
  await page.goto('/models/snap_nope');
  await expect(page.getByRole('alert')).toContainText('Model not found');
});
