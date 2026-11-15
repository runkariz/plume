import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** A tab opened before a deploy asks for a lazy chunk that is gone: reload once, then a calm error page. */
for (const theme of THEMES) {
  test.describe(`error page (${theme})`, () => {
    test.use({ theme });

    test('a lazy chunk that cannot be loaded reloads once, then shows the error page, never the router screen', async ({
      page,
      context,
    }) => {
      let attempts = 0;
      // at the context: the mock service worker answers page requests, so only the context sees the real fetch
      await context.route(/ModelView/, (route) => {
        attempts += 1;
        return route.abort();
      });
      await page.goto('/models');
      await page.getByRole('region', { name: 'Official models' }).getByRole('link').first().click();
      await expect(
        page.getByRole('heading', { name: 'A new version of Plume is available' }),
      ).toBeVisible({ timeout: 15_000 });
      expect(attempts, 'one failed load, one reload, then it stops').toBeGreaterThanOrEqual(2);
      expect(attempts).toBeLessThan(6);
      await expect(page.getByText('Unexpected Application Error')).toHaveCount(0);
      // the header stays, and Home leads out
      await expect(page.getByRole('link', { name: 'Plume home' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Reload' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-error-page', theme);
      await page.getByRole('link', { name: 'Home', exact: true }).click();
      await expect(page).toHaveURL(/\/$/);
    });
  });
}
