import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Package notices as the real API sends them. Needs the real Kaufland package loaded as `kaufland` (one auth notice,
 * five manifest warnings) and a Shopify copy whose manifest.json warns with
 * auth-requires-signature / default-environment-by-order / knowledge-links: PLUME_E2E_NOTICES=true.
 */
const NOTICES = process.env.PLUME_E2E_NOTICES === 'true';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`package notices, real data (${theme})`, () => {
    test.skip(
      !NOTICES,
      'set PLUME_E2E_NOTICES=true with the Kaufland and warned Shopify packages loaded',
    );
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('Kaufland: a package without auth schemes says there is no ready option', async ({
      page,
    }) => {
      await page.goto('/apis/kaufland?section=auth');
      const card = page.getByRole('region', { name: 'Authentication' });
      await expect(card.getByRole('list', { name: 'Notes on this package' })).toContainText(
        'Every request must be signed',
      );
      await expect(card).toContainText('Not in this package');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w32-real-auth-notice', theme);
    });

    test('Kaufland: the five warnings only for a maintainer', async ({ page }) => {
      await page.goto('/apis/kaufland');
      await expect(page.getByRole('region', { name: 'Package warnings' })).toHaveCount(0);
      await signIn(page);
      await page.goto('/apis/kaufland');
      const warnings = page.getByRole('region', { name: 'Package warnings' });
      await expect(warnings).toContainText('Package warnings (5)');
      await expect(warnings).toContainText('auth-requires-signature');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(warnings, 'w32-real-package-warnings', theme);
    });

    test('Shopify (warned copy): both notes, three warnings for a maintainer', async ({ page }) => {
      await page.goto('/apis/shopify?section=auth');
      await expect(
        page
          .getByRole('region', { name: 'Authentication' })
          .getByRole('list', { name: 'Notes on this package' }),
      ).toBeVisible();
      const env = page.getByRole('region', { name: 'Environments' });
      await expect(env).toContainText('Choose your region');
      await shotOf(env, 'w32-real-environments-notice', theme);
      await signIn(page);
      await page.goto('/apis/shopify');
      await expect(
        page.getByRole('region', { name: 'Package warnings' }).getByRole('listitem'),
      ).toHaveCount(3);
    });
  });
}
