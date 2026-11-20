import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Check call, ambiguous: several operations share POST /sync; the examples are buttons that fill `method=<name>`. */
for (const theme of THEMES) {
  test.describe(`check call, ambiguous (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a warning with the note and the examples; a pick fills the parameter and checks again', async ({
      page,
    }) => {
      await page.goto('/apis/shopify/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption('POST');
      await page.getByLabel('Path').fill('/sync');
      await page.getByLabel('Parameters, comma separated').fill('app_key');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Several operations share this method and path')).toBeVisible();
      await expect(page.getByRole('note')).toContainText('ambiguous: 156 operations');
      const picks = page.getByRole('group', { name: 'Examples to pick' }).getByRole('button');
      await expect(picks).toHaveCount(3);
      await page.getByText('Some of the operations at this path').click();
      await settle(page);
      await expectNoSeriousA11y(page);
      const card = page
        .getByText('Several operations share this method and path')
        .locator('xpath=ancestor::*[contains(@class,"card")][1]');
      await shotOf(card, 'w41-check-ambiguous', theme);
      await picks.first().click();
      await expect(page.getByLabel('Parameters, comma separated')).toHaveValue(
        'app_key, method=aliexpress.affiliate.category.get',
      );
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      await shotOf(
        page
          .getByText('Documented', { exact: true })
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w41-check-picked',
        theme,
      );
    });
  });
}
