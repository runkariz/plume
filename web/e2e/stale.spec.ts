import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/**
 * The docs of a model's APIs changed after it was built. The server says how that touches the model (`impact`): the
 * page leads with the affected mappings, and a maintainer's Regenerate opens a new session. A model the server sent no
 * impact for keeps the old stale mark.
 */
for (const theme of THEMES) {
  test.describe(`model with newer docs (${theme})`, () => {
    test.use({ theme });

    test('chip, impact banner with the mappings, a maintainer regenerates into a model to review', async ({
      page,
    }) => {
      await page.goto('/maintainer');
      await page.getByLabel('Email').fill('maintainer@example.com');
      await page.getByLabel('Access token').fill('pl_e2e_token_value');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
      await page.goto('/models/m-38f24111baf1076f44c9cfa7');
      await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible();
      await expect(page.getByText('⚠ 2 affected (1 breaking)')).toBeVisible();
      await expect(page.getByTestId('impact-banner')).toContainText(
        '2 mappings affected (1 breaking)',
      );
      await expect(page.getByRole('list', { name: 'Affected mappings' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w10-stale-model', theme);

      // a maintainer's Regenerate generates on the server and lands on the unreleased model, waiting for review
      await page.getByRole('link', { name: 'Regenerate' }).click();
      await expect(page.getByText('Unreleased: waiting for your review')).toBeVisible();
      await expect(page).toHaveURL(/\/models\/m-job1/);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w10-regenerate-session', theme);
    });

    test('the models page lists models with their impact instead of the stale mark', async ({
      page,
    }) => {
      await page.goto('/models');
      const list = page.getByRole('region', { name: 'Official models' });
      await expect(list.getByRole('link', { name: 'Order', exact: true })).toBeVisible();
      // the Order over all three APIs and the one over Shopify + WooCommerce are both touched
      await expect(list.getByText('⚠ 2 affected (1 breaking)')).toHaveCount(2);
      await expect(list.getByText('Docs updated, unaffected')).toHaveCount(1);
      // the impact replaces the blanket stale mark
      await expect(list.getByText('Stale')).toHaveCount(0);
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
