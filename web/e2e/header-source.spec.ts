import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Where the auth header comes from: the vendor's quote, or the OAuth 2.0 standard's label in the open (no quote). */
const NOTE = "OAuth 2.0 standard (RFC 6750), not stated in the vendor's docs";

for (const theme of THEMES) {
  test.describe(`header source (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the auth list and the scheme pages', async ({ page }) => {
      await page.goto('/apis/stripe?section=auth');
      const list = page.getByRole('region', { name: 'Authentication' });
      await expect(list.getByText('Authorization: Bearer <token>')).toHaveCount(2);
      await expect(list.getByText(NOTE)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(list, 'w45-header-list', theme);
      await page.goto('/apis/stripe/auth/oauth2-connect');
      const std = page.getByRole('region', { name: 'How it works' });
      await expect(std.getByText(NOTE)).toBeVisible();
      await expect(std.locator('blockquote')).toHaveCount(0);
      await shotOf(std, 'w45-header-standard', theme);
      await page.goto('/apis/stripe/auth/api-key');
      const vendor = page.getByRole('region', { name: 'How it works' });
      await expect(vendor.locator('blockquote')).toContainText('secret key');
      await expectNoSeriousA11y(page);
      await shotOf(vendor, 'w45-header-vendor', theme);
    });
  });
}
