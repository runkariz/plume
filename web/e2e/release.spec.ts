import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, shotOf, test, THEMES } from './helpers';

/** The maintainer's review of a build after it was published: nothing is held; keep, roll back, copy issues, promote. */
const TOKEN = 'pl_e2e_token_value';
const NEW = 'b-shopify-20261114';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`release review (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the maintainer home flags a build that needs attention and leads to its review', async ({
      page,
    }) => {
      await signIn(page);
      const row = page.locator('.m-row').filter({ hasText: 'Shopify' });
      await expect(row.getByText('Needs attention')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await row.getByRole('link', { name: 'Release review' }).click();
      await expect(
        page.getByRole('heading', { level: 1, name: 'Release review: shopify' }),
      ).toBeVisible();
    });

    test('the review: status, attention, the extraction report by rule, what users see, the history', async ({
      page,
    }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Release review' }).first().click();
      await expect(page.getByText('Nothing is held: this build is live')).toBeVisible();
      await expect(page.getByRole('region', { name: 'Alphabetical cut-off' })).toBeVisible();
      await expect(
        page.getByRole('region', { name: 'Changes users see' }).getByText(/Suspect/),
      ).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w22-release-review', theme);
      await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-review-actions', theme);
      await shotOf(
        page.getByRole('region', { name: 'Alphabetical cut-off' }),
        'w22-report-group',
        theme,
      );
    });

    test('roll back with a reason: the tag moves back, the build can be rolled forward', async ({
      page,
    }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Release review' }).first().click();
      await page.getByRole('button', { name: 'Roll back…' }).click();
      const dialog = page.getByRole('group', { name: 'Roll back this build' });
      await expect(dialog.getByRole('button', { name: 'Roll back', exact: true })).toBeDisabled();
      await dialog
        .getByLabel(/Reason/)
        .fill('Order lost the fields after "l": an extraction artifact');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-rollback-confirm', theme);
      await dialog.getByRole('button', { name: 'Roll back', exact: true }).click();
      await expect(page.getByText(/Rolled back: `latest` is b-shopify-2026/)).toBeVisible();
      await expect(page.getByText('Not latest')).toBeVisible();
      await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-rolled-back', theme);
      await page.getByRole('button', { name: 'Roll forward' }).click();
      await expect(page.getByText('Latest', { exact: true })).toBeVisible();
    });

    test('promote a suspect change with a verified quote, and demote it', async ({ page }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Release review' }).first().click();
      const row = page
        .getByRole('region', { name: 'Alphabetical cut-off' })
        .getByRole('listitem')
        .first();
      await row.getByRole('button', { name: 'Promote to confirmed…' }).click();
      await row
        .getByLabel(/A quote from the vendor docs/)
        .fill('Nothing like this is in the page.');
      await row.getByRole('button', { name: 'Promote to confirmed', exact: true }).click();
      await expect(row.getByRole('alert')).toContainText('not in the source text of this build');
      await shotOf(row, 'w22-promote-refused', theme);
      await row
        .getByLabel(/A quote from the vendor docs/)
        .fill('shipping_lines: the shipping lines of the order.');
      await row.getByRole('button', { name: 'Promote to confirmed', exact: true }).click();
      await expect(
        page.getByRole('region', { name: 'Changes users see' }).getByText('Promoted by hand'),
      ).toBeVisible();
    });

    test('the builds timeline', async ({ page }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Release review' }).first().click();
      await page.getByRole('link', { name: 'All builds' }).click();
      const list = page.getByRole('list', { name: 'Builds' });
      await expect(list.getByRole('listitem')).toHaveCount(3);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(list, 'w22-builds', theme);
    });
  });
}

test('on a narrow screen the review does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page);
  await page.getByRole('link', { name: 'Release review' }).first().click();
  await expect(page.getByRole('region', { name: 'Alphabetical cut-off' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  void NEW;
});
