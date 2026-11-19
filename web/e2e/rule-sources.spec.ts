import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Rules the package states on several pages: "Stated on N pages", the first three links, then all of them. */
const GUIDE = encodeURIComponent('guide:pagination');

for (const theme of THEMES) {
  test.describe(`rule sources (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a rule on five pages shows three links and "Show all"; a document without any shows nothing', async ({
      page,
    }) => {
      await page.goto(`/apis/shopify/documents/${GUIDE}`);
      const card = page.getByRole('region', { name: 'Rule sources' });
      await expect(card).toContainText('Stated on 5 pages');
      const list = card.getByRole('list', { name: /^Pages of List endpoints return/ });
      await expect(list.getByRole('link')).toHaveCount(3);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w36-rule-sources', theme);
      await card.getByRole('button', { name: 'Show all 5' }).click();
      await expect(list.getByRole('link')).toHaveCount(5);
      await shotOf(card, 'w36-rule-sources-all', theme);
      await page.goto(`/apis/shopify/documents/${encodeURIComponent('guide:rate-limits')}`);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Rule sources' })).toHaveCount(0);
    });
  });
}
