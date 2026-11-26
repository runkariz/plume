import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Conditions and property-level conflicts on a live package: Meta Commerce (meta-commerce-platform-20261127d-extras,
 * loaded as `meta-commerce-platform`). POST /{ORDER_ID}/refunds states conditions ("field retailer_id required ..."),
 * which are not a disagreement; the transaction-detail model has a disagreement about transaction_type:
 * PLUME_E2E_META=true.
 */
const ON = process.env.PLUME_E2E_META === 'true';
const doc = (id: string) => `/apis/meta-commerce-platform/documents/${encodeURIComponent(id)}`;

for (const theme of THEMES) {
  test.describe(`conditions and property conflicts, real data (${theme})`, () => {
    test.skip(!ON, 'needs meta-commerce-platform (coord/LIVE): PLUME_E2E_META=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the refunds endpoint shows its conditions, and no disagreement', async ({ page }) => {
      await page.goto(doc('endpoint:POST~/{ORDER_ID}/refunds'));
      const card = page.getByRole('region', { name: 'Conditions' });
      await expect(card.getByRole('heading', { level: 3 })).toHaveCount(3);
      await expect(card).toContainText(
        'Condition on items[].retailer_id (required only in this case):',
      );
      await expect(page.getByRole('region', { name: 'Conflicting statements' })).toHaveCount(0);
      await expect(page.getByText('The docs disagree')).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w53-real-refunds-conditions', theme);
    });

    test('the transaction-detail model shows the disagreement about transaction_type', async ({
      page,
    }) => {
      await page.goto(doc('model:transaction-detail'));
      const card = page.getByRole('region', { name: 'Conflicting statements' });
      await expect(card).toContainText('The docs state different values for transaction_type:');
      await expect(card).toContainText(
        'transaction_type values: the payments page allows SALE or REFUND',
      );
      await expect(card.getByRole('listitem')).toHaveCount(3);
      await expect(page.getByRole('region', { name: 'Conditions' })).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w53-real-transaction-detail', theme);
    });

    test('check call says a conditional field that was sent has a condition, on its own lines', async ({
      page,
    }) => {
      await page.goto('/apis/meta-commerce-platform/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption('POST');
      await page.getByLabel('Path').fill('/{ORDER_ID}/refunds');
      await page.getByLabel('Parameters, comma separated').fill('items[].retailer_id');
      await page.getByRole('button', { name: 'Check' }).click();
      // names match only in full: the nested field is passed with its path
      const item = page.getByRole('listitem').filter({ hasText: 'items[].retailer_id' }).first();
      await expect(item).toContainText(
        'Condition on items[].retailer_id (required only in this case):',
      );
      await expect(item).toContainText('Required if item_id is not provided.');
      // the server's lines stay lines
      expect((await item.locator('.param-note p').innerText()).split('\n').length).toBeGreaterThan(
        1,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(item, 'w53-real-check-call-condition', theme);
    });
  });
}
