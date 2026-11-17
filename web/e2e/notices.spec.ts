import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Package notices on the auth and environments sections, and the package warnings list (maintainers only). */
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`package notices (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the auth section shows the note above the schemes', async ({ page }) => {
      await page.goto('/apis/stripe?section=auth');
      const card = page.getByRole('region', { name: 'Authentication' });
      await expect(card.getByRole('list', { name: 'Notes on this package' })).toContainText(
        'Every request must be signed',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w32-auth-notice', theme);
    });

    test('the environments card shows its note; warnings only after sign-in', async ({ page }) => {
      await page.goto('/apis/shopify');
      const env = page.getByRole('region', { name: 'Environments' });
      await expect(env).toContainText('first one listed is used');
      await shotOf(env, 'w32-environments-notice', theme);
      await expect(page.getByRole('region', { name: 'Package warnings' })).toHaveCount(0);
      await signIn(page);
      await page.goto('/apis/shopify');
      const warnings = page.getByRole('region', { name: 'Package warnings' });
      await expect(warnings.getByRole('listitem')).toHaveCount(5);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(warnings, 'w32-package-warnings', theme);
    });
  });
}

test('375 px: notes and warnings do not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page);
  for (const url of ['/apis/stripe?section=auth', '/apis/shopify']) {
    await page.goto(url);
    await expect(page.getByRole('list', { name: 'Notes on this package' })).toBeVisible();
    await settle(page);
    const wide = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(wide, url).toBe(false);
  }
});
