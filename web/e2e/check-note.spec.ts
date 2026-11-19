import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Check call: the request carries only keys the server accepts (422 otherwise), and the server's note is shown. */
for (const theme of THEMES) {
  test.describe(`check call note (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a path that is not documented shows why', async ({ page }) => {
      const sent: Record<string, unknown>[] = [];
      page.on('request', (r) => {
        if (r.method() === 'POST' && r.url().includes('/check-call'))
          sent.push(r.postDataJSON() as Record<string, unknown>);
      });
      await page.goto('/apis/shopify/try');
      await page.getByRole('radio', { name: 'Check call' }).check({ force: true });
      await page.getByLabel('Path').fill('/admin/api/2020-01/orders.json');
      await page.getByRole('button', { name: 'Check' }).click();
      const note = page.getByRole('note');
      await expect(note).toContainText('The documented operation is GET');
      expect(sent.length).toBeGreaterThan(0);
      for (const body of sent)
        expect(
          Object.keys(body).filter(
            (k) => !['method', 'path', 'params', 'query', 'body', 'version'].includes(k),
          ),
        ).toEqual([]);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page
          .getByText('Not documented in build')
          .locator('xpath=ancestor::*[contains(@class,"card")][1]'),
        'w38-check-note',
        theme,
      );
    });
  });
}
