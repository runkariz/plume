import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Check call on AliExpress, where 156 operations share POST /sync and the `method` value picks one: the verdict is
 * "ambiguous", the examples are buttons. Needs the real AliExpress package loaded as `aliexpress`:
 * PLUME_E2E_ALIEXPRESS=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_ALIEXPRESS === 'true';

for (const theme of THEMES) {
  test.describe(`check call ambiguous, real data (${theme})`, () => {
    test.skip(!ON, 'needs the real AliExpress package: PLUME_E2E_ALIEXPRESS=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('POST /sync is ambiguous; a picked example is documented', async ({ page, request }) => {
      const res = await request.post(`${API}/v1/apis/aliexpress/check-call`, {
        data: { method: 'POST', path: '/sync', params: [] },
      });
      const body = (await res.json()) as {
        verdict: string;
        note: string;
        pick: { param: string; options: { value: string; docId: string }[] } | null;
      };
      expect(body.verdict).toBe('ambiguous');
      expect(body.note).toContain('pass method=<name>');
      expect(body.pick?.param).toBe('method');
      const total = body.pick?.options.length ?? 0;
      expect(total).toBeGreaterThan(100);
      await page.goto('/apis/aliexpress/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption('POST');
      await page.getByLabel('Path').fill('/sync');
      await page.getByLabel('Parameters, comma separated').fill('');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Several operations share this method and path')).toBeVisible();
      const picks = page.getByRole('list', { name: 'Operations to pick' }).getByRole('button');
      await expect(page.getByText(`${total} operations, the first 8 shown`)).toBeVisible();
      await expect(picks).toHaveCount(8); // the first matches; the filter narrows the rest
      const label = (await picks.first().textContent()) ?? '';
      expect(label).toMatch(/^method=\S+$/);
      // a filter finds one of the 156
      const filter = page.getByRole('searchbox', { name: 'Filter the operations' });
      await filter.fill('affiliate.category');
      await expect(picks.first()).toContainText('affiliate.category');
      await filter.fill('');
      await settle(page);
      await expectNoSeriousA11y(page);
      const card = page
        .getByText('Several operations share this method and path')
        .locator('xpath=ancestor::*[contains(@class,"card")][1]');
      await shotOf(card, 'w41-real-aliexpress-ambiguous', theme);
      await picks.first().click();
      await expect(page.getByLabel('Parameters, comma separated')).toHaveValue(label);
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      await shotOf(
        page
          .getByText('Documented', { exact: true })
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w41-real-aliexpress-picked',
        theme,
      );
    });
  });
}
