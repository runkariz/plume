import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** The payload of a webhook event: fields and sample, or a link to the model it is. */
for (const theme of THEMES) {
  test.describe(`trigger payload (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('fields and a collapsed sample', async ({ page }) => {
      await page.goto('/apis/shopify/triggers/orders%2Fcreate');
      const fields = page.getByRole('region', { name: 'Payload fields' });
      await expect(fields).toContainText('line_items[].sku');
      const sample = page.getByLabel('Sample payload');
      await expect(sample).toBeHidden();
      await page.getByText('Sample payload, as in the package').click();
      await expect(sample).toContainText('"sku": "A-1"');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w31-payload-fields', theme);
    });

    test('a model payload links to the model', async ({ page }) => {
      await page.goto('/apis/shopify/triggers/app%2Funinstalled');
      const head = page.getByRole('region', { name: 'Payload' });
      await expect(head).toContainText('The payload is the model');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(head, 'w31-payload-model', theme);
      await head.getByRole('link', { name: 'Order' }).click();
      await expect(page).toHaveURL(/\/documents\/model%3Aorder$/);
    });
  });
}

test('375 px: the payload does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/apis/shopify/triggers/orders%2Fcreate');
  await expect(page.getByRole('region', { name: 'Payload fields' })).toBeVisible();
  const wide = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(wide).toBe(false);
});
