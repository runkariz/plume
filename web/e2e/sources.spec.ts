import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Where the docs came from: the public API page, and the maintainer's review of a build. */
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`sources (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the API page: linked sources and "Extracted on" next to docs as of', async ({ page }) => {
      await page.goto('/apis/shopify');
      const line = page.getByTestId('sources-line');
      await expect(line).toContainText('Sources: Docs · OpenAPI spec · Changelog');
      await expect(line).toContainText(
        'Extracted on 14 Nov 2026 from docs, OpenAPI spec, changelog',
      );
      await expect(line.getByRole('link', { name: 'OpenAPI spec' })).toHaveAttribute(
        'href',
        'https://shopify.dev/openapi/admin-rest.json',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.titlerow'), 'w24-api-sources', theme);
    });

    test('the review: sources, the run, conflicts, and units that were not compared', async ({
      page,
    }) => {
      await signIn(page);
      // in the app: a page.goto would reset the mock server
      await page
        .locator('.m-row')
        .filter({ hasText: 'Shopify' })
        .getByRole('link', { name: 'Release review' })
        .click();
      const panel = page.getByRole('region', { name: 'Sources and conflicts' });
      await expect(panel).toBeVisible();
      await expect(panel).toContainText('run-20261114-0830');
      await expect(panel.getByTestId('conflict-check')).toContainText('6 units not compared');
      await expect(panel).toContainText('<script>alert(1)</script> 100');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(panel, 'w24-review-sources', theme);
    });
  });
}

test('375 px: the sources line wraps and the page does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/apis/shopify');
  await expect(page.getByTestId('sources-line')).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});
