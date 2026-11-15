import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

async function uploadShopify(page: Page) {
  await page.getByRole('link', { name: 'Update knowledge' }).first().click();
  await expect(page.getByRole('heading', { name: /^Update / })).toBeVisible();
  await page.getByLabel('Choose package file').setInputFiles({
    name: 'shopify-package.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from('zip'),
  });
  await expect(page.getByText('Archive is safe')).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`maintainer wizard (${theme})`, () => {
    test.use({ theme });

    test('sign-in screen, then the wizard: upload → review → build (SSE) → publish', async ({
      page,
    }) => {
      await page.goto('/maintainer');
      await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w3-03-sign-in', theme);

      await signIn(page);
      // for this tab only (sessionStorage, one key), never in localStorage
      expect(await page.evaluate(() => JSON.stringify({ ...localStorage }))).not.toContain(TOKEN);
      expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([
        'plume-maintainer-session',
      ]);

      // 1 Upload
      await uploadShopify(page);
      await expect(page.getByLabel('API id')).toHaveValue('shopify');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w3-04-wizard-upload', theme);

      // 2 Review
      await page.getByRole('button', { name: 'Review changes →' }).click();
      await expect(page.getByText('Embedding plan')).toBeVisible();
      await expect(page.getByText('Nothing goes live yet')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w3-05-wizard-review', theme);

      // 3 Build: the events arrive over SSE and the pipeline fills in
      await page.getByRole('button', { name: 'Start build' }).click();
      await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
      await expect(page.getByText('Package accepted · 1,118 files · 0.4 s')).toBeVisible();
      const next = page.getByRole('button', { name: 'Review quality gate →' });
      await expect(next).toBeEnabled({ timeout: 30_000 });
      await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
      await expectNoSeriousA11y(page);
      await next.click();

      // 4 Publish
      await expect(page.getByText('Quality gate passed')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w3-07-wizard-publish', theme);
      await page.getByRole('button', { name: 'Publish 2026-11-14' }).click();
      await expect(page.getByText('Published 2026-11-14')).toBeVisible();
      await page.getByRole('link', { name: 'View Shopify Admin REST' }).click();
      await expect(page).toHaveURL(/\/apis\/shopify$/);
    });

    test('build screen mid-stream (frozen at batch 3 of 4)', async ({ page }) => {
      await page.addInitScript(() => localStorage.setItem('plume-mock-pause-at', 'mid'));
      await signIn(page);
      await uploadShopify(page);
      await page.getByRole('button', { name: 'Review changes →' }).click();
      await page.getByRole('button', { name: 'Start build' }).click();
      await expect(page.getByText('Batch 3 of 4 · 32 of 50 chunks')).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByText('Live', { exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Review quality gate →' })).toBeDisabled();
      await expect(page.getByText('32 / 50')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w3-06-wizard-build-live', theme);
    });
  });
}

test('wizard pages need a sign-in', async ({ page }) => {
  await page.goto('/maintainer/apis/shopify/update');
  await expect(page.getByLabel('Access token')).toBeVisible();
  await expect(page).toHaveURL(/\/maintainer$/);
});

test('a wrong token is refused and nothing is stored', async ({ page }) => {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill('wrong');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('That token was not accepted');
});
