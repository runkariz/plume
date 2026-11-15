import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test } from '../e2e/helpers';

/** The maintainer session against the real API: it survives a refresh, and a token the API refuses ends it. */
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const KEY = 'plume-maintainer-session';

test('sign in, refresh: still signed in; Sign out ends it', async ({ page }) => {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage }))).not.toContain(TOKEN);
  expect(page.url()).not.toContain(TOKEN);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
  expect(await page.evaluate((k) => sessionStorage.getItem(k), KEY)).toBeNull();
});

test('a stored token the real API refuses (401) returns to sign-in with the reason', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(
    (k) =>
      sessionStorage.setItem(
        k,
        JSON.stringify({
          key: 'pl_stale_token_that_the_server_forgot',
          name: 'old',
          generation: null,
        }),
      ),
    KEY,
  );
  await page.goto('/models'); // the "Waiting for review" list asks the API with the token
  await expect(page.getByRole('alert')).toContainText('Your session ended');
  await expect(page.getByLabel('Access token')).toBeVisible();
  expect(await page.evaluate((k) => sessionStorage.getItem(k), KEY)).toBeNull();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w15-real-session-expired', 'light');
  // and signing in again works
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
});
