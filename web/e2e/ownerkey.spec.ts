import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** The owner key: pasted on the Models page (from another browser, or from the view in Claude), and "other versions". */
const DEMO_KEY = 'ok-demo-3f9a0c71d2e84b5f';

for (const theme of THEMES) {
  test.describe(`owner key and other versions (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('paste a key to list your models; a mistyped key is refused and not kept', async ({
      page,
    }) => {
      await page.goto('/models');
      const region = page.getByRole('region', { name: 'Add an owner key' });
      await expect(region).toBeVisible();
      await expect(page.getByRole('region', { name: 'Your models' })).toHaveCount(0);
      await region.getByText(/Have an owner key/).click();
      await region.getByLabel('Owner key').fill('ok-typo');
      await region.getByRole('button', { name: 'Add key' }).click();
      await expect(region.getByRole('alert')).toContainText(
        'No model or model set belongs to this key',
      );
      await region.getByLabel('Owner key').fill(DEMO_KEY);
      await region.getByRole('button', { name: 'Add key' }).click();
      await expect(region.getByRole('status')).toContainText('Added: 1 model');
      await expect(page.getByRole('region', { name: 'Your models' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w18-owner-key-paste', theme);
      // kept in this browser (a reload still lists them), and never in the address
      expect(page.url()).not.toContain(DEMO_KEY);
      await page.reload();
      await expect(page.getByRole('region', { name: 'Your models' })).toBeVisible();
    });

    test('a model names the other official models of its concept', async ({ page }) => {
      await page.goto('/models/m-order0lder0a1b2c3d4e5f60718293a4b5c');
      await expect(page.getByText(/Other official models of this concept/)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w18-same-concept', theme);
      await page
        .getByText(/Other official models of this concept/)
        .getByRole('link')
        .click();
      await expect(page).not.toHaveURL(/m-order0lder/);
    });
  });
}
