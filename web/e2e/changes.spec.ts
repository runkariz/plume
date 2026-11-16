import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** What users see of release notes: the docs-updated badge, the Changes tab, and the impact on models and sets. */
for (const theme of THEMES) {
  test.describe(`what changed (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the home card and the API header say docs were updated and lead to the Changes tab', async ({
      page,
    }) => {
      await page.goto('/');
      const card = page.locator('.api-card').filter({ hasText: 'Shopify Admin REST' });
      const badge = card.getByRole('link', {
        name: /Docs updated 14 Nov 2026: 3 changes, 2 breaking/,
      });
      await expect(badge).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w25-home-card-badge', theme);
      await badge.click();
      await expect(page.getByRole('region', { name: /^Changes of / })).toBeVisible();
    });

    test('the Changes tab: timeline, filters with true counts, items grouped by document, wording apart', async ({
      page,
    }) => {
      await page.goto('/apis/shopify');
      await page.locator('.seg label').filter({ hasText: 'Changes' }).click();
      const panel = page.getByRole('region', { name: /^Changes of / });
      await expect(
        panel.getByRole('region', { name: 'GET /admin/api/latest/orders.json' }),
      ).toBeVisible();
      await expect(panel.locator('.pills label').filter({ hasText: /^Breaking/ })).toContainText(
        '2',
      );
      await expect(panel).toContainText("Per the vendor's changelog");
      await expect(panel).toContainText('Wording only: 1 description changed.');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('region', { name: 'Builds with changes' }),
        'w25-changes-timeline',
        theme,
      );
      await shotOf(panel, 'w25-changes-list', theme);
      await panel
        .locator('.pills label')
        .filter({ hasText: /^Breaking/ })
        .click();
      await expect(panel.getByText(/note_attributes/)).toHaveCount(0);
      await expect(page).toHaveURL(/filter=breaking/);
      await shotOf(panel, 'w25-changes-breaking', theme);
    });

    test('the models page: an impact chip per model, and a model page that leads with the affected mappings', async ({
      page,
    }) => {
      await page.goto('/models');
      const list = page.getByRole('region', { name: 'Official models' });
      await expect(list).toContainText('2 affected (1 breaking)');
      await expect(list).toContainText('Docs updated, unaffected');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(list, 'w25-models-list-impact', theme);
      await list.getByRole('link', { name: 'Order', exact: true }).click();
      const banner = page.getByTestId('impact-banner');
      await expect(banner).toContainText('2 mappings affected (1 breaking)');
      await expect(banner.getByRole('list', { name: 'Affected mappings' })).toBeVisible();
      await expectNoSeriousA11y(page);
      await shotOf(banner, 'w25-model-impact-banner', theme);
    });

    test('a set page: the set status, each member, the affected mappings with their member', async ({
      page,
    }) => {
      await page.goto('/models');
      await page
        .getByRole('region', { name: 'Official model sets' })
        .getByRole('link', { name: 'Shop' })
        .click();
      const banner = page.getByTestId('impact-banner');
      await expect(banner).toContainText('3 mappings affected (1 breaking)');
      await expect(banner.getByRole('list', { name: 'Impact per model' })).toBeVisible();
      await expectNoSeriousA11y(page);
      await shotOf(banner, 'w25-set-impact-banner', theme);
    });

    test('a maintainer renames an API; the new name shows on the home page', async ({ page }) => {
      await page.goto('/maintainer');
      await page.getByLabel('Email').fill('maintainer@example.com');
      await page.getByLabel('Access token').fill('pl_e2e_token_value');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('button', { name: 'Rename Shopify Admin REST' }).click();
      await shotOf(page.locator('.m-row').filter({ hasText: 'Shopify' }), 'w25-rename-open', theme);
      await page.getByLabel('Display name of shopify').fill('Shopify Admin');
      await page.getByRole('button', { name: 'Save name' }).click();
      await expect(page.getByRole('button', { name: 'Rename Shopify Admin' })).toBeVisible();
      await expect(page.locator('.m-row').filter({ hasText: 'Shopify' })).toContainText('Renamed');
      await expectNoSeriousA11y(page);
    });
  });
}

test.describe('at 375 px', () => {
  test.use({ viewport: { width: 375, height: 800 } });
  for (const path of [
    '/',
    '/apis/shopify?section=changes',
    '/apis/shopify?section=changes&filter=breaking',
    '/models',
  ])
    test(`${path} does not scroll sideways`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
      await settle(page);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
      ).toBe(false);
    });
});
