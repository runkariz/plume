import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Check call with a path that carries the base path of a declared server: the matched endpoint says "via server ...".
 * Real eBay Commerce package (ebay-commerce-20261120a) loaded as `ebay-commerce`, POST /commerce/media/v1_beta/video:
 * PLUME_E2E_EBAY=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_EBAY === 'true';
const PATH = '/commerce/media/v1_beta/video';

for (const theme of THEMES) {
  test.describe(`matched server, real data (${theme})`, () => {
    test.skip(!ON, 'needs the real eBay Commerce package: PLUME_E2E_EBAY=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the matched endpoint is shown with the server whose base path the call carried', async ({
      page,
      request,
    }) => {
      const res = await request.post(`${API}/v1/apis/ebay-commerce/check-call`, {
        data: { method: 'POST', path: PATH, params: [] },
      });
      const body = (await res.json()) as { matched: { server?: string | null } };
      expect(body.matched.server).toContain('https://apim.ebay.com/commerce/media/v1_beta');
      await page.goto('/apis/ebay-commerce/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('HTTP method').selectOption('POST');
      await page.getByLabel('Path').fill(PATH);
      await page.getByLabel('Parameters, comma separated').fill('');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByText('Documented', { exact: true })).toBeVisible();
      await expect(page.getByText(/via server/)).toContainText(
        'api_3: https://apim.ebay.com/commerce/media/v1_beta',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page
          .getByText('Documented', { exact: true })
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w48-real-matched-server',
        theme,
      );
    });
  });
}
