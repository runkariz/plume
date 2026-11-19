import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Check call on the real API: the strict request (an unknown key is a 422) and the note that says why a path
 * matching a template is not documented. Needs the real Amazon package loaded as `amazon-sp-vendor`
 * (GET /vendor/orders/v1/purchaseOrders is fixed at v1): PLUME_E2E_AMAZON=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const AMAZON = process.env.PLUME_E2E_AMAZON === 'true';

for (const theme of THEMES) {
  test.describe(`check call note, real data (${theme})`, () => {
    test.skip(!AMAZON, 'needs the real Amazon package: PLUME_E2E_AMAZON=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the server refuses an unknown key; the web sends none, and shows the note', async ({
      page,
      request,
    }) => {
      const refused = await request.post(`${API}/v1/apis/amazon-sp-vendor/check-call`, {
        data: { method: 'GET', path: '/x', params: [], bogus: 1 },
      });
      expect(refused.status()).toBe(422);
      const sent: Record<string, unknown>[] = [];
      page.on('request', (r) => {
        if (r.method() === 'POST' && r.url().includes('/check-call'))
          sent.push(r.postDataJSON() as Record<string, unknown>);
      });
      await page.goto('/apis/amazon-sp-vendor/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('Path').fill('/vendor/orders/v9/purchaseOrders');
      await page.getByLabel('Parameters, comma separated').fill('');
      await page.getByRole('button', { name: 'Check' }).click();
      await expect(page.getByRole('note')).toContainText(
        'the documented operation is GET /vendor/orders/v1/purchaseOrders',
      );
      expect(sent).toHaveLength(1);
      expect(
        Object.keys(sent[0] ?? {}).filter(
          (k) => !['method', 'path', 'params', 'query', 'body', 'version'].includes(k),
        ),
      ).toEqual([]);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page
          .getByText(/Not documented in build/)
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w38-real-check-note',
        theme,
      );
    });
  });
}
