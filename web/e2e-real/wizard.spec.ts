import { expect, type Page } from '@playwright/test';
import { zipSync } from 'fflate';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * The maintainer wizard against the real API (P4): sign in, upload a zipped fixture package,
 * review the diff, watch the real SSE build, publish, and download the dump.
 *
 * Needs the stack started with a maintainer token (PLUME_MAINTAINER_TOKENS='["pl_dev_local"]' make up)
 * and the same token in PLUME_E2E_TOKEN (default pl_dev_local). The fixture packages are zipped here,
 * from the repo's tests/fixtures/packages, so the API under test receives a real upload.
 *
 * The specs run one after the other (they publish and change the live build of the same API).
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const PACKAGES = resolve(
  fileURLToPath(new URL('.', import.meta.url)),
  '../../tests/fixtures/packages',
);

function zipPackage(name: string): Buffer {
  const root = join(PACKAGES, name);
  const files: Record<string, Uint8Array> = {};
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else files[relative(root, full).split('\\').join('/')] = readFileSync(full);
    }
  };
  walk(root);
  return Buffer.from(zipSync(files));
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

/** The key lives in memory only, so after sign-in navigate inside the app (page.goto would sign out). */
async function openUpdate(page: Page, apiId: string) {
  await page.locator(`a[href="/maintainer/apis/${apiId}/update"]`).click();
  await expect(page.getByRole('heading', { name: /^Update / })).toBeVisible();
}

async function upload(page: Page, apiId: string, pkg: string) {
  await openUpdate(page, apiId);
  await page.getByLabel('Choose package file').setInputFiles({
    name: `${pkg}.zip`,
    mimeType: 'application/zip',
    buffer: zipPackage(pkg),
  });
  await expect(
    page
      .getByText('Known package schema')
      .or(page.getByText(/schema|contract/i))
      .first(),
  ).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

test('a wrong token is refused by the real API', async ({ page }) => {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill('definitely-wrong');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('That token was not accepted');
});

test('the real API rejects maintainer calls without a token and non-zip uploads', async ({
  request,
}) => {
  const noAuth = await request.get(`${API}/v1/maintainer/me`);
  expect(noAuth.status()).toBe(401);
  const bad = await request.post(`${API}/v1/packages`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    multipart: { file: { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('x') } },
  });
  expect(bad.status()).toBe(415);
  expect((await bad.json()).detail).toBe('Only .zip packages are accepted');
});

for (const theme of THEMES) {
  test.describe(`real wizard (${theme})`, () => {
    test.use({ theme });

    test('sign in, upload, review, build over SSE, publish, download', async ({ page }) => {
      await page.goto('/maintainer');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w6-real-sign-in', theme);

      await signIn(page);
      expect(
        await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage })),
      ).not.toContain(TOKEN);

      // 1 upload: the real server validates the zip
      await upload(page, 'test-catalog-api', 'test-catalog');
      await expect(page.getByText('test-catalog.zip')).toBeVisible();
      await expect(page.getByLabel('API id')).toHaveValue('test-catalog-api');
      await expect(page.getByRole('button', { name: 'Review changes →' })).toBeEnabled();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w6-real-upload', theme);

      // 2 review: a real diff against the live build and an embedding plan
      await page.getByRole('button', { name: 'Review changes →' }).click();
      await expect(page.getByText('Embedding plan')).toBeVisible();
      await expect(page.getByText('Nothing goes live yet')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w6-real-review', theme);

      // 3 build: real SSE events fill the pipeline
      await page.getByRole('button', { name: 'Start build' }).click();
      await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();
      const next = page.getByRole('button', { name: 'Review quality gate →' });
      await expect(next).toBeEnabled({ timeout: 60_000 });
      await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', /^\d+$/);
      await expect(page.getByText('Live events')).toBeVisible();
      await expect(
        page
          .locator('[role=log]')
          .getByText(/postgres|gemini|plume/)
          .first(),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w6-real-build-done', theme);
      await next.click();

      // 4 publish: the gate result is real (a gold set exists for test-catalog-api)
      await expect(page.getByRole('heading', { name: 'Release' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w6-real-publish', theme);

      const download = page.waitForEvent('download', { timeout: 15_000 });
      await page.getByRole('button', { name: 'Download dump' }).click();
      // an on-page error (e.g. a failed request) would show up here with its text
      await expect(page.getByRole('alert')).toHaveCount(0);
      expect((await download).suggestedFilename()).toMatch(/\.gz$/);

      await page.getByRole('button', { name: /^Publish / }).click();
      await expect(page.getByText(/^Published /)).toBeVisible();
      await page.getByRole('link', { name: /^View / }).click();
      await expect(page).toHaveURL(/\/apis\/test-catalog-api$/);
      await expect(page.getByText('latest')).toBeVisible();
    });
  });
}

test('a package for another API is blocked in the UI before the server says no', async ({
  page,
}) => {
  await signIn(page);
  await openUpdate(page, 'second-catalog-api');
  await page.getByLabel('Choose package file').setInputFiles({
    name: 'test-catalog.zip',
    mimeType: 'application/zip',
    buffer: zipPackage('test-catalog'),
  });
  await expect(page.getByRole('alert')).toContainText('This package is for “test-catalog-api”');
  await expect(page.getByRole('button', { name: 'Review changes →' })).toBeDisabled();
});
