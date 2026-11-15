import { expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * WRITE_ONLY_SOURCE against the real API: a mapping whose only citation is the request body of a write. It needs the
 * test-catalog package WITH a POST /api/{version}/orders (the package of tests/fixtures plus a copy of the GET
 * orders endpoint with method POST, as the backend's own test makes it); the default fixtures have none, so this
 * spec runs only with PLUME_E2E_WRITE_ONLY=true after loading such a package (see web/README.md).
 */
const ENABLED = process.env.PLUME_E2E_WRITE_ONLY === 'true';
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const auth = { Authorization: `Bearer ${TOKEN}` };
const POST_DOC = 'endpoint:POST~/api/{version}/orders';
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as {
  fields: { name: string; sources: Record<string, Record<string, unknown>> }[];
};
const RUN = Date.now().toString(36);

test.skip(!ENABLED, 'needs a test-catalog with a POST /orders: PLUME_E2E_WRITE_ONLY=true');

for (const theme of THEMES) {
  test.describe(`write-only warnings, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the server warns, the model page and the review banner show it, linked to the field', async ({
      page,
      request,
    }) => {
      const started = (await (
        await request.post(`${API}/v1/models/generate`, {
          headers: auth,
          data: { apis: APIS, concept: 'Order', engine: 'claude', force: true },
        })
      ).json()) as { sessionId: string };
      const doc = (await (
        await request.get(`${API}/v1/apis/${APIS[0]}/documents/${encodeURIComponent(POST_DOC)}`)
      ).json()) as { fields: { name: string; description?: string | null }[] };
      const spec = doc.fields.find((f) => f.description && f.name.endsWith('number'));
      expect(spec, 'the POST document has a described number field').toBeTruthy();
      const draft = structuredClone(good);
      const number = draft.fields.find((f) => f.name === 'number');
      expect(number).toBeTruthy();
      if (number)
        number.sources[APIS[0] as string] = {
          paths: [{ path: spec?.name }],
          evidence: [{ doc_id: POST_DOC, quote: spec?.description }], // no GET fetch: a write only
        };
      const res = await request.post(`${API}/v1/models/sessions/${started.sessionId}/draft`, {
        headers: auth,
        data: { ...draft, name: `Order write-only ${RUN}-${theme}` },
      });
      expect(res.status(), await res.text()).toBe(201);
      const model = (
        (await res.json()) as {
          model: { id: string; warnings: { code: string; field: string; api: string }[] };
        }
      ).model;
      expect(model.warnings.map((w) => [w.code, w.field, w.api])).toEqual([
        ['WRITE_ONLY_SOURCE', 'number', APIS[0]],
      ]);

      await page.goto('/maintainer');
      await page.getByLabel('Access token').fill(TOKEN);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
      await page.goto(`/models/${model.id}`);
      const list = page.getByRole('region', { name: '1 mapping cites only a request body' });
      await expect(list).toBeVisible();
      await expect(
        page.getByText('Before you release: 1 mapping cites only a request body'),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.access-banner').first(), 'w20-real-review-banner', theme);
      await shotOf(list, 'w20-real-warnings', theme);
      // the warning links to the mapping it is about, and the detail says so
      await list.getByRole('link', { name: 'number' }).click();
      await expect(page).toHaveURL(new RegExp(`field=number&api=${APIS[0]}`));
      await expect(page.getByRole('note')).toContainText(/request body|write/i);
    });
  });
}
