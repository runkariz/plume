import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** What a mapping does to the value: a chip per mapped API field, opening to the enum map, format and note. */
for (const theme of THEMES) {
  test.describe(`mapping conversions (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the table shows a chip per converted field; the detail shows it in full', async ({
      page,
    }) => {
      await page.goto('/models/snap_8f3a21');
      await page.getByRole('radio', { name: 'Table' }).click({ force: true });
      const table = page.getByRole('table');
      const row = table.getByRole('row').filter({ hasText: 'allow_backorder' });
      await expect(row.getByText('enum map')).toHaveCount(2);
      // a field with no conversion shows no chip
      await expect(
        table.getByRole('row').filter({ hasText: 'low_stock_threshold' }).locator('.conv'),
      ).toHaveCount(0);
      await row.getByText('enum map').first().click();
      await expect(
        row.getByRole('list', { name: 'enum map: API value to canonical value' }).first(),
      ).toContainText('continue → true');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(table, 'w37-table-conversions', theme);

      await page.goto('/models/snap_8f3a21?field=allow_backorder&api=shopify');
      const detail = page.getByRole('region', { name: 'Mapping detail' });
      await expect(detail.getByText('Conversion')).toBeVisible();
      await expect(detail.getByText('deny').locator('xpath=ancestor::li')).toContainText('false');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(detail, 'w37-detail-conversion', theme);
    });
  });
}
