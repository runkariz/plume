import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Mapping reports (maintainer): the list with its tab, one report (current vs suggested, citation, validator), the decision. */
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`mapping reports (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the tab, the list, a report with its citation, accepting it', async ({ page }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Reported questions' }).first().click();
      await page
        .getByRole('navigation', { name: 'Kinds of reports' })
        .getByRole('link', { name: 'Mapping reports' })
        .click();
      const list = page.getByRole('list', { name: 'Mapping reports' });
      await expect(list.getByRole('listitem')).toHaveCount(6);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w51-mapping-list', theme);
      await list.getByRole('link').first().click();
      const compare = page.getByRole('region', { name: 'Current and suggested mapping' });
      await expect(compare.locator('mark')).toContainText('Total amount billed for the order.');
      await expect(compare.getByRole('group', { name: 'Validator result' })).toContainText(
        'Passed the validator',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w51-mapping-report', theme);
      const decide = page.getByRole('form', { name: 'Decide' });
      await decide.getByLabel('Reason').fill('Per-location is what clients need.');
      await decide.getByRole('button', { name: 'Accept' }).click();
      await expect(decide.getByText('Accepted: it is now a verified mapping.')).toBeVisible();
      await expect(page.getByRole('region', { name: 'Verified mapping' })).toBeVisible();
      await shotOf(page.locator('main'), 'w51-mapping-accepted', theme);
    });

    test('a failed suggestion, and the verified mappings on the model page', async ({ page }) => {
      await signIn(page);
      await page.goto('/maintainer/mapping-reports/mr-9z8y7x6w5v');
      const compare = page.getByRole('region', { name: 'Current and suggested mapping' });
      await expect(compare.getByRole('group', { name: 'Validator result' })).toContainText(
        'FIELD_NOT_FOUND',
      );
      await expect(
        page.getByRole('form', { name: 'Decide' }).getByRole('button', { name: 'Accept' }),
      ).toBeDisabled();
      await shotOf(compare, 'w51-mapping-failed', theme);
      await page.goto('/maintainer/mapping-reports/mr-8d7c6b5a4e');
      const absence = page.getByRole('region', { name: 'Suggested mapping', exact: true });
      await expect(absence).toContainText('Not available on shopify');
      await shotOf(
        page.getByRole('region', { name: 'Current and suggested mapping' }),
        'w51-mapping-absence',
        theme,
      );
      await page.goto('/models/snap_8f3a21');
      const verified = page.getByRole('region', { name: 'Verified mappings' });
      await expect(verified).toContainText('verified (user report mr-5t4s3r2q1p)');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(verified, 'w51-model-verified', theme);
    });
  });
}

test('375 px: the list and a report do not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page);
  for (const url of ['/maintainer/mapping-reports', '/maintainer/mapping-reports/mr-1a2b3c4d5e']) {
    await page.goto(url);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await settle(page);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
});
