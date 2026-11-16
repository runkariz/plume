import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shotOf, test } from '../e2e/helpers';

/**
 * Removing an API against the real API, cross-origin from the dev server (a DELETE with a JSON body and the bearer
 * token). It removes `second-catalog-api` from the stack, so it runs last (the file name sorts after the others) and is
 * gated: PLUME_E2E_REMOVE=true. An unreleased Order over test-catalog-api + second-catalog-api pins it.
 */
test.skip(process.env.PLUME_E2E_REMOVE !== 'true', 'removes an API: PLUME_E2E_REMOVE=true');

const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const REMOVE = 'second-catalog-api';
const auth = { Authorization: `Bearer ${TOKEN}` };
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as object;

async function draft(request: APIRequestContext, name: string): Promise<string> {
  const started = (await (
    await request.post(`${API}/v1/models/generate`, {
      headers: auth,
      data: { apis: ['test-catalog-api', REMOVE], concept: 'Order', engine: 'claude', force: true },
    })
  ).json()) as { sessionId: string };
  const res = await request.post(`${API}/v1/models/sessions/${started.sessionId}/draft`, {
    headers: auth,
    data: { ...good, name },
  });
  expect(res.status(), await res.text()).toBe(201);
  return ((await res.json()) as { model: { id: string } }).model.id;
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

test.use({ viewport: { width: 1280, height: 900 } });

test('remove an API that a draft pins: listed, forced, retired, gone', async ({
  page,
  request,
}) => {
  const name = `Remove check ${Date.now().toString(36)}`;
  const modelId = await draft(request, name);
  const preview = (await (
    await request.get(`${API}/v1/apis/${REMOVE}/removal`, { headers: auth })
  ).json()) as {
    pinnedBy: { type: string; id: string; name: string }[];
  };
  expect(preview.pinnedBy.map((p) => p.id)).toContain(modelId);

  await signIn(page);
  const row = page.locator('.m-row').filter({ hasText: 'Second Catalog API' });
  await row.getByRole('button', { name: /^Remove / }).click();
  const panel = page.getByRole('group', { name: `Remove ${REMOVE}` });
  const list = panel.getByRole('list', { name: /use this API/ });
  await expect(list).toContainText(name);
  const remove = panel.getByRole('button', { name: `Remove ${REMOVE}` });
  await panel.getByLabel(new RegExp(`Type ${REMOVE} to confirm`)).fill('wrong');
  await panel.getByRole('checkbox').check();
  await expect(remove).toBeDisabled();
  await panel.getByLabel(new RegExp(`Type ${REMOVE} to confirm`)).fill(REMOVE);
  await panel.getByLabel(/Reason/).fill('web e2e check');
  await settle(page);
  await expectNoSeriousA11y(page);
  await shotOf(panel, 'w27-real-remove-panel', 'light');
  await remove.click();
  const notice = page.getByRole('status').filter({ hasText: `Removed ${REMOVE}` });
  await expect(notice).toContainText(name);
  await expect(notice).toContainText(/now (superseded|discarded)/);
  // sets have no "superseded": an official or unreleased set is "discarded" (when z-sets.spec.ts ran before)
  for (const set of preview.pinnedBy.filter((p) => p.type === 'set'))
    await expect(notice.getByText(set.name).first()).toBeVisible();
  for (const li of await notice.locator('li').filter({ hasText: /^set / }).all())
    await expect(li).toContainText('now discarded');
  await shotOf(notice, 'w27-real-remove-done', 'light');
  await expect(page.locator('.m-row').filter({ hasText: REMOVE })).toHaveCount(0);

  // the server agrees: the API is gone and the model is retired
  expect((await request.get(`${API}/v1/apis/${REMOVE}`)).status()).toBe(404);
  const m = (await (
    await request.get(`${API}/v1/models/${modelId}`, { headers: auth })
  ).json()) as {
    visibility?: string;
  };
  expect(['discarded', 'superseded']).toContain(m.visibility);
});
