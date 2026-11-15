import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, shotOf, test, THEMES } from './helpers';

/** W20: the running job's clock and heartbeat, warnings, the release choice (supersedes) and retiring older models. */
const TOKEN = 'pl_e2e_token_value';
const UNRELEASED = 'm-unrel0a1b2c3d4e5f60718293a4b5c6d7e8f';
const UNRELEASED_ORDER = 'm-unrelorder0a1b2c3d4e5f60718293a4b5c';
const OFFICIAL_ORDER_SW = 'm-ordersw0a1b2c3d4e5f60718293a4b5c6d7';
const OLDER = 'm-order0lder0a1b2c3d4e5f60718293a4b5c';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`W20 (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a long model call: the server heartbeat and a clock that keeps going', async ({
      page,
    }) => {
      // the mock job stops at its first heartbeat and stays running
      await page.addInitScript(() => localStorage.setItem('plume-mock-hold-job', '1'));
      await signIn(page);
      await page.goto('/models/suggest?apis=shopify,woocommerce,mirakl');
      await page.getByRole('button', { name: 'Generate Shipment', exact: true }).click();
      const panel = page.getByRole('region', { name: 'Generation on the server' });
      await expect(panel.getByText('Waiting for the model, 0:12 (round 1 of 3)')).toBeVisible();
      const clock = panel.locator('.live .mono');
      await expect(clock).toHaveText(/^0:1[2-9]$/);
      const first = await clock.textContent();
      // the clock moves between heartbeats: a long round does not look frozen
      await expect.poll(async () => clock.textContent(), { timeout: 5000 }).not.toBe(first);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(panel, 'w20-job-clock', theme);
    });

    test('warnings: counted in the review banner, listed on the page, linked to the mapping', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(`/models/${UNRELEASED}`);
      const list = page.getByRole('region', { name: '3 mappings cite only a request body' });
      await expect(list).toBeVisible();
      await expect(list.getByRole('listitem')).toHaveCount(3);
      await expect(
        page.getByText('Before you release: 3 mappings cite only a request body'),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-review-banner', theme);
      await shotOf(list, 'w20-warnings', theme);
      await list.getByRole('link', { name: 'title' }).click();
      await expect(page).toHaveURL(/field=title&api=mirakl/);
      await expect(page.getByRole('note')).toContainText(
        'product_title is documented only in the request body',
      );
      await shot(page, 'w20-warning-detail', theme);
    });

    test('release asks which older official Orders it replaces; the replaced one says "Superseded by"', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(`/models/${UNRELEASED_ORDER}`);
      await page.getByRole('button', { name: 'Release' }).click();
      const dialog = page.getByRole('group', { name: /Does this model replace an official one\?/ });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('checkbox')).toHaveCount(3);
      for (const box of await dialog.getByRole('checkbox').all())
        await expect(box).not.toBeChecked();
      const sw = dialog.locator('li').filter({ hasText: OFFICIAL_ORDER_SW });
      await expect(sw.getByText('covered by this model')).toBeVisible();
      await expect(sw.getByText('stale')).toBeVisible();
      const all = dialog.locator('li').filter({ hasText: OLDER });
      await expect(all.getByText('not covered: Mirakl')).toBeVisible();
      await all.getByRole('checkbox').check();
      await expect(dialog.getByRole('status')).toContainText(
        'takes that API out of the official lists',
      );
      await all.getByRole('checkbox').uncheck();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-release-dialog', theme);
      await sw.getByRole('checkbox').check();
      await dialog.getByRole('button', { name: 'Release and replace 1' }).click();
      await expect(
        page.getByText(/Replaced these official models when it was released/),
      ).toContainText(OFFICIAL_ORDER_SW);
      // in the app (a reload would reset the mock server): the replaced model is one click away
      await page
        .getByText(/Replaced these official models when it was released/)
        .getByRole('link', { name: OFFICIAL_ORDER_SW })
        .click();
      await expect(page.getByText(`Superseded by ${UNRELEASED_ORDER}`)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-superseded', theme);
    });

    test('from an official model: retire older models of the concept', async ({ page }) => {
      await signIn(page);
      await page.goto(`/models/${OFFICIAL_ORDER_SW}`);
      const panel = page.getByRole('region', { name: 'Retire older models' });
      await panel.getByRole('button', { name: 'Retire older models of this concept' }).click();
      const dialog = panel.getByRole('group', { name: /Retire older models of this concept/ });
      await expect(dialog.getByRole('button', { name: 'Retire' })).toBeDisabled();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(panel, 'w20-retire', theme);
      await dialog.locator('li').filter({ hasText: OLDER }).getByRole('checkbox').check();
      await dialog.getByRole('button', { name: 'Retire 1' }).click();
      await expect(page.getByText(/Replaced these official models/)).toContainText(OLDER);
      await page
        .getByText(/Replaced these official models/)
        .getByRole('link', { name: OLDER })
        .click();
      await expect(page.getByText(`Superseded by ${OFFICIAL_ORDER_SW}`)).toBeVisible();
    });
  });
}

test('on a narrow screen the release choice does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page);
  await page.goto(`/models/${UNRELEASED_ORDER}`);
  await page.getByRole('button', { name: 'Release' }).click();
  await expect(page.getByRole('group', { name: /replace an official one/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
