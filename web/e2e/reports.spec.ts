import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from './helpers';

/** Reported questions (maintainer): the list, one report with its notes, the triage form. */
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`reported questions (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the list, filtered by status; a report with its notes; saving a status', async ({
      page,
    }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Reported questions' }).click();
      const list = page.getByRole('list', { name: 'Reports' });
      await expect(list.getByRole('listitem')).toHaveCount(4);
      await expect(list.getByRole('listitem').first()).toContainText('4 reports');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w49-reports-list', theme);
      await page.getByRole('radio', { name: 'Out of scope' }).click({ force: true });
      await expect(list.getByRole('listitem')).toHaveCount(1);
      await page.getByRole('radio', { name: 'All' }).click({ force: true });

      await list.getByRole('link').first().click();
      await expect(page.getByRole('region', { name: 'The report' })).toContainText('page_info');
      const notes = page.getByRole('list', { name: 'Notes on this report' });
      await expect(notes.getByRole('listitem')).toHaveCount(3);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w49-report-detail', theme);

      const form = page.getByRole('form', { name: 'Triage' });
      await form.getByRole('radio', { name: 'Out of scope' }).click({ force: true });
      await expect(form).toContainText('Readers see this reason');
      await form
        .getByLabel('Reason')
        .fill('Paging with other filters is not documented by the vendor.');
      await form.getByRole('button', { name: 'Save status' }).click();
      await expect(form.getByText('Saved.')).toBeVisible();
      await shotOf(page.getByRole('region', { name: 'Triage' }), 'w49-report-triage', theme);
    });
  });
}

test('375 px: the list and a report do not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page);
  for (const url of ['/maintainer/reports', '/maintainer/reports/rq-1a2b3c4d5e']) {
    await page.goto(url);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await settle(page);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
});
