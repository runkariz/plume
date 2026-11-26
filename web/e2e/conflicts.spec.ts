import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** The docs state different values for a limit: every statement with its place, examples marked, none picked. */
for (const theme of THEMES) {
  test.describe(`conflicting statements (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('an endpoint whose docs disagree lists every statement', async ({ page }) => {
      await page.goto(`/apis/shopify/documents/${encodeURIComponent('endpoint:GET~/orders.json')}`);
      const card = page.getByRole('region', { name: 'Conflicting statements' });
      await expect(card).toContainText('The docs state different values for page size:');
      await expect(card.getByRole('listitem')).toHaveCount(5);
      await expect(card).toContainText('different values for orders[].financial_status:');
      // a condition is not a disagreement: its own card
      const conditions = page.getByRole('region', { name: 'Conditions' });
      await expect(conditions).toContainText('Condition on ids (send it only when this applies):');
      await expect(card).not.toContainText('Required if since_id');
      await expect(card.getByText('example', { exact: true })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w53-conflicts', theme);
      await shotOf(conditions, 'w53-conditions', theme);
    });
  });
}
