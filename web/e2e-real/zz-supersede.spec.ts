import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Releasing a model that replaces older official models of its concept, and retiring them later, against the real
 * API. Three Order models over the two catalog APIs, each in its own lineage (a new session, a maintainer draft).
 * The file name sorts last: what it releases must not change what the other specs see.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const auth = { Authorization: `Bearer ${TOKEN}` };
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as object;
const RUN = Date.now().toString(36);

/** A new Order lineage stored unreleased (a maintainer's draft). */
async function draft(request: APIRequestContext, name: string): Promise<string> {
  const started = (await (
    await request.post(`${API}/v1/models/generate`, {
      headers: auth,
      data: { apis: APIS, concept: 'Order', engine: 'claude', force: true },
    })
  ).json()) as { sessionId: string };
  const res = await request.post(`${API}/v1/models/sessions/${started.sessionId}/draft`, {
    headers: auth,
    data: { ...good, name },
  });
  expect(res.status(), await res.text()).toBe(201);
  return ((await res.json()) as { model: { id: string } }).model.id;
}

async function release(request: APIRequestContext, id: string, supersedes?: string[]) {
  const res = await request.post(`${API}/v1/models/${id}/release`, {
    headers: auth,
    ...(supersedes ? { data: { supersedes } } : {}),
  });
  expect(res.status(), await res.text()).toBe(200);
  return (await res.json()) as { visibility: string; supersedes?: string[] };
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`supersede, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('release asks which older official Orders it replaces; they become "Superseded by" and leave the lists', async ({
      page,
      request,
    }) => {
      const a = await draft(request, `Order A ${RUN}-${theme}`);
      await release(request, a); // official
      const b = await draft(request, `Order B ${RUN}-${theme}`); // unreleased: the one to release
      // the server's own candidate list (maintainer token only)
      const cand = (await (
        await request.get(`${API}/v1/models/${b}/supersedable`, { headers: auth })
      ).json()) as { items: { id: string; covered: boolean; apis: string[]; stale: boolean }[] };
      const ca = cand.items.find((i) => i.id === a);
      expect(ca, 'the official Order A is a candidate').toMatchObject({ covered: true });
      expect((await request.get(`${API}/v1/models/${b}/supersedable`)).status()).toBe(401);

      await signIn(page);
      await page.goto(`/models/${b}`);
      await page.getByRole('button', { name: 'Release' }).click();
      const dialog = page.getByRole('group', { name: /Does this model replace an official one\?/ });
      await expect(dialog).toBeVisible();
      const row = dialog.locator('li').filter({ hasText: a });
      await expect(row.getByText('covered by this model')).toBeVisible();
      await expect(row.getByRole('checkbox')).not.toBeChecked(); // nothing is ticked for the maintainer
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-real-release-dialog', theme);
      await row.getByRole('checkbox').check();
      await dialog.getByRole('button', { name: /^Release and replace \d+$/ }).click();
      await expect(page.getByText('Official', { exact: true }).first()).toBeVisible();
      await expect(
        page.getByText(/Replaced these official models when it was released/),
      ).toContainText(a);

      // A: readable by id, "Superseded by B", out of the official list
      await page.goto(`/models/${a}`);
      await expect(page.getByText(`Superseded by ${b}`)).toBeVisible();
      await expect(page.getByText('Superseded', { exact: true }).first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-real-superseded', theme);
      const gone = (await (await request.get(`${API}/v1/models`)).json()) as {
        items: { id: string }[];
      };
      expect(gone.items.map((i) => i.id)).not.toContain(a);
      expect(gone.items.map((i) => i.id)).toContain(b);
      const old = (await (await request.get(`${API}/v1/models/${a}`)).json()) as Record<
        string,
        unknown
      >;
      expect(old).toMatchObject({ visibility: 'superseded', supersededBy: b });
    });

    test('from an official model, retire older ones after the fact', async ({ page, request }) => {
      const older = await draft(request, `Order older ${RUN}-${theme}`);
      await release(request, older);
      const newer = await draft(request, `Order newer ${RUN}-${theme}`);
      await release(request, newer); // official, nothing replaced

      await signIn(page);
      await page.goto(`/models/${newer}`);
      const panel = page.getByRole('region', { name: 'Retire older models' });
      await panel.getByRole('button', { name: 'Retire older models of this concept' }).click();
      const dialog = panel.getByRole('group', { name: /Retire older models of this concept/ });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole('button', { name: 'Retire' })).toBeDisabled();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(panel, 'w20-real-retire', theme);
      await dialog.locator('li').filter({ hasText: older }).getByRole('checkbox').check();
      await dialog.getByRole('button', { name: /^Retire \d+$/ }).click();
      await expect(page.getByText(/Replaced these official models/)).toContainText(older);
      const o = (await (await request.get(`${API}/v1/models/${older}`)).json()) as Record<
        string,
        unknown
      >;
      expect(o).toMatchObject({ visibility: 'superseded', supersededBy: newer });
    });
  });
}

test('the server refuses to replace something that is not an official model of the concept (409), and changes nothing', async ({
  request,
}) => {
  const target = await draft(request, `Order refuse ${RUN}`);
  const res = await request.post(`${API}/v1/models/${target}/release`, {
    headers: auth,
    data: { supersedes: ['m-not-a-model'] },
  });
  expect(res.status()).toBe(409);
  const still = (await (
    await request.get(`${API}/v1/models/${target}`, { headers: auth })
  ).json()) as {
    visibility: string;
  };
  expect(still.visibility).toBe('unreleased');
});
