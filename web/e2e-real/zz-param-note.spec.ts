import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * A parameter check with a note: a paging name that is not in the endpoint's documented parameters but that the API's
 * paging guide uses. Real WooCommerce package (woocommerce-v3-20261119a-extras, loaded as `woocommerce`): GET coupons/{id}
 * with `offset`. Where the server sends `guideId` the guide is linked; otherwise the note is shown alone:
 * PLUME_E2E_PARAM_NOTE=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_PARAM_NOTE === 'true';
const PATH = '/wp-json/wc/{version}/coupons/{id}';

for (const theme of THEMES) {
  test.describe(`param check note, real data (${theme})`, () => {
    test.skip(!ON, 'needs the real WooCommerce package: PLUME_E2E_PARAM_NOTE=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the note is shown under the parameter; the guide is linked when the server names it', async ({
      page,
      request,
    }) => {
      const res = await request.post(`${API}/v1/apis/woocommerce/check-call`, {
        data: { method: 'GET', path: PATH, params: ['offset'] },
      });
      const body = (await res.json()) as {
        paramChecks: {
          name: string;
          found: boolean;
          note?: string | null;
          guideId?: string | null;
        }[];
      };
      const check = body.paramChecks[0];
      expect(check?.found).toBe(false);
      expect(check?.note).toContain('Paging for this API is described in');
      await page.goto('/apis/woocommerce/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('Path').fill(PATH);
      await page.getByLabel('Parameters, comma separated').fill('offset');
      await page.getByRole('button', { name: 'Check' }).click();
      const item = page.getByRole('listitem').filter({ hasText: 'offset' }).first();
      await expect(item).toContainText('missing');
      await expect(item).toContainText("Not in this endpoint's documented parameters");
      if (check?.guideId) {
        const link = item.getByRole('list', { name: 'Guide for offset' }).getByRole('link');
        await expect(link).toHaveAttribute('href', new RegExp(encodeURIComponent(check.guideId)));
      } else {
        await expect(item.getByRole('link')).toHaveCount(0);
      }
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page
          .getByText(/Documented|Not documented/)
          .first()
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w46-real-param-note',
        theme,
      );
    });
  });
}
