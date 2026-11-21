import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Check call: a documented call that leaves out required parameters. The fixtures' Shopify POST products.json requires
 * a `product` body and a Content-Type header: a bare call is still "documented", with `missingRequired` and the note.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const PATH = '/admin/api/2026-10/products.json';

for (const theme of THEMES) {
  test.describe(`missing required, real data (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a bare call is documented, and the required fields it left out are listed', async ({
      page,
      request,
    }) => {
      const res = await request.post(`${API}/v1/apis/shopify/check-call`, {
        data: { method: 'POST', path: PATH, params: [] },
      });
      const body = (await res.json()) as {
        verdict: string;
        note: string | null;
        missingRequired?: Record<string, string[]>;
      };
      expect(body.verdict).toBe('documented');
      expect(body.missingRequired?.body).toContain('product');
      expect(body.note).toContain('required fields are missing');
      await page.goto('/apis/shopify/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption('POST');
      await page.getByLabel('Path').fill(PATH);
      await page.getByLabel('Parameters, comma separated').fill('');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      const missing = page.getByRole('group', { name: 'Required fields the call did not pass' });
      await expect(missing).toContainText('product');
      await expect(missing).toContainText('Content-Type');
      await expect(page.getByRole('note')).toContainText('required fields are missing');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page
          .getByText('Documented', { exact: true })
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w50-real-missing-required',
        theme,
      );
    });
  });
}
