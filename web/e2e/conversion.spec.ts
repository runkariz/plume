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
      const table = page.getByRole('table', { name: /How each API fills/ });
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

    test('the Operations section: a row per operation, a column per API, endpoints linked', async ({
      page,
    }) => {
      await page.goto('/models/snap_8f3a21');
      const card = page.getByRole('region', { name: 'Operations' });
      await expect(card.getByRole('rowheader')).toHaveCount(3);
      const set = card.getByRole('row').filter({ hasText: 'set absolute stock' });
      await expect(set).toContainText('absolute; omitted means 0');
      await expect(set).toContainText('No equivalent');
      await expect(
        card.getByRole('row').filter({ hasText: 'adjust stock by a delta' }),
      ).toContainText('delta');
      await set.getByText('1 citation').click();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w38-operations', theme);
      await set.getByRole('link').first().click();
      await expect(page).toHaveURL(/\/apis\/shopify\/documents\/endpoint%3APOST/);
    });

    test('not mapped values and a citation without a quote', async ({ page }) => {
      await page.goto('/models/snap_8f3a21');
      await page.getByRole('radio', { name: 'Table' }).click({ force: true });
      const fields = page.getByRole('table', { name: /How each API fills/ });
      const row = fields.getByRole('row').filter({ hasText: 'allow_backorder' });
      await row.getByText('enum map').nth(1).click();
      await expect(row).toContainText('not mapped: preorder, on_request');
      const stock = fields.getByRole('row').filter({ hasText: 'manage_stock' });
      await stock.getByText('1 citation').nth(1).click();
      await expect(stock).toContainText('cited without quote: the field');
      await settle(page);
      await shotOf(
        page.getByRole('table', { name: /How each API fills/ }),
        'w38-unmapped-noquote',
        theme,
      );
    });
  });
}
