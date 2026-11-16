import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** What the package says about an API: rate limits, the vendor's real path, field constraints; and Remove API. */
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`package details (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the API page shows the rate limits; Browse shows the real paths', async ({ page }) => {
      await page.goto('/apis/amazon-sp-vendor');
      const card = page.getByRole('region', { name: 'Rate limits' });
      await expect(card).toContainText('leaky-bucket');
      await expect(card).toContainText('x-amzn-RateLimit-Limit');
      await expect(page.getByRole('link', { name: /^\/vendor\/orders\/v1/ }).first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w27-rate-limits-api', theme);
    });

    test('an endpoint shows its limit and the allowed values of its fields', async ({ page }) => {
      await page.goto('/apis/amazon-sp-vendor/documents/endpoint:get-orders');
      await expect(page.getByRole('region', { name: 'Rate limit' })).toContainText('10 per 60 s');
      const query = page.getByRole('region', { name: 'Query parameters' });
      await expect(query).toContainText('one of open | closed | cancelled');
      await expect(query).toContainText('value 1–250');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w27-endpoint-details', theme);
    });

    test('Remove API: the models and sets are listed, force and the typed id are needed', async ({
      page,
    }) => {
      await signIn(page);
      const row = page.locator('.m-row').filter({ hasText: 'Stripe' });
      await row.getByRole('button', { name: /^Remove / }).click();
      const panel = page.getByRole('group', { name: 'Remove stripe' });
      await expect(panel.getByRole('list', { name: /use this API/ })).toBeVisible();
      const remove = panel.getByRole('button', { name: 'Remove stripe' });
      await panel.getByLabel(/Type stripe to confirm/).fill('stripe');
      await expect(remove).toBeDisabled();
      await panel.getByRole('checkbox').check();
      await expect(remove).toBeEnabled();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(panel, 'w27-remove-panel', theme);
      await remove.click();
      const notice = page.getByRole('status').filter({ hasText: 'Removed stripe' });
      await expect(notice).toContainText('Retired');
      await expect(page.locator('.m-row').filter({ hasText: 'Stripe' })).toHaveCount(0);
      await shotOf(notice, 'w27-remove-done', theme);
    });
  });
}

test('375 px: the remove panel and the endpoint page do not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/apis/amazon-sp-vendor/documents/endpoint:get-orders');
  await expect(page.getByRole('region', { name: 'Rate limit' })).toBeVisible();
  const wide = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(wide).toBe(false);
  await signIn(page);
  await page
    .locator('.m-row')
    .filter({ hasText: 'Stripe' })
    .getByRole('button', { name: /^Remove / })
    .click();
  await expect(page.getByRole('group', { name: 'Remove stripe' })).toBeVisible();
  const wide2 = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(wide2).toBe(false);
});
