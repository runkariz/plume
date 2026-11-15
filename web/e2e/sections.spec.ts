import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** Browse items are links; Auth, Triggers (with the "not in this package" state), Environments and the icon. */
for (const theme of THEMES) {
  test.describe(`package sections (${theme})`, () => {
    test.use({ theme });

    test('browse → endpoint detail, with the package icon in the header', async ({ page }) => {
      await page.goto('/apis/shopify');
      await expect(page.locator('.ep-link').first()).toBeVisible();
      // the package's own icon, served by the API, never an external URL
      const icon = page.locator('.title-left img');
      await expect(icon).toHaveAttribute('src', /\/v1\/apis\/shopify\/icon$/);
      await expect
        .poll(() => icon.evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0);
      await expect(page.getByRole('region', { name: 'Environments' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-browse-icon-environments', theme);

      await page.locator('a.ep-link', { hasText: '/admin/api/latest/orders.json' }).nth(1).click();
      await expect(page).toHaveURL(/\/documents\//);
      for (const name of [
        'Query parameters',
        'Headers',
        'Request body',
        'Response fields',
        'Responses',
      ])
        await expect(page.getByRole('region', { name })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-endpoint-detail', theme);
    });

    test('authentication: list and scheme detail', async ({ page }) => {
      await page.goto('/apis/shopify');
      await page.getByRole('radio', { name: /^Authentication/ }).click({ force: true });
      await expect(page).toHaveURL(/section=auth/);
      await expect(page.getByRole('link', { name: 'OAuth2 authorization code' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-auth-list', theme);
      await page.getByRole('link', { name: 'OAuth2 authorization code' }).click();
      await expect(page.getByRole('region', { name: 'Scopes' })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Setup steps' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-auth-scheme', theme);
    });

    test('triggers: list, event detail, and the empty state for a package without any', async ({
      page,
    }) => {
      await page.goto('/apis/shopify?section=triggers');
      await expect(page.getByRole('link', { name: 'app/scopes_update' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-triggers-list', theme);
      await page.getByRole('link', { name: 'app/scopes_update' }).click();
      await expect(
        page.getByRole('heading', { level: 1, name: 'app/scopes_update' }),
      ).toBeVisible();
      await expect(page.getByLabel('Event JSON')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-trigger-detail', theme);

      await page.goto('/apis/stripe?section=triggers');
      await expect(page.getByRole('heading', { name: 'Not in this package' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w11-triggers-empty', theme);
    });
  });
}

test('an API without an icon keeps the letter tile; Environments render nothing when absent', async ({
  page,
}) => {
  await page.goto('/apis/stripe');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.locator('.title-left img')).toHaveCount(0);
  await expect(page.locator('.title-left .logo')).toHaveText('St');
  await expect(page.getByRole('region', { name: 'Environments' })).toHaveCount(0);
});
