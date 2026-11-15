import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, openControls, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * Nested canonical fields against the real API: a model whose `amounts` field is an object with `total` and
 * `currency` inside it. The file name sorts last: the model it stores must not change what the other specs see.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const auth = { Authorization: `Bearer ${TOKEN}` };
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as {
  fields: { name: string }[];
};
const RUN = Date.now().toString(36);

interface Created {
  id: string;
  fields: { name: string; path?: string; fields?: { name: string; path?: string }[] }[];
  coverage: Record<string, { mapped: number; total: number }>;
}

async function createNested(request: APIRequestContext): Promise<Created> {
  const session = (await (
    await request.post(`${API}/v1/models/generate`, {
      headers: auth,
      data: { apis: APIS, concept: 'order', engine: 'claude', force: true },
    })
  ).json()) as { sessionId: string };
  const byName = Object.fromEntries(good.fields.map((f) => [f.name, f]));
  const draft = {
    ...good,
    name: `Order nested ${RUN}`,
    fields: [
      byName.id,
      byName.number,
      // an object with no sources of its own: its sub-fields are the mappings
      {
        name: 'amounts',
        type: 'object',
        description: 'Money of the order',
        fields: [byName.total, byName.currency],
      },
      byName.customer,
    ],
  };
  const res = await request.post(`${API}/v1/models/sessions/${session.sessionId}/draft`, {
    headers: auth,
    data: draft,
  });
  expect(res.status(), await res.text()).toBe(201);
  return ((await res.json()) as { model: Created }).model;
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

/** The field names of the table rows (without the toggle's glyph). */
const names = (page: Page) =>
  page.locator('table.mtable-grid th[scope="row"] .mtable-name').evaluateAll((els) =>
    els.map((el) =>
      [...el.childNodes]
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent)
        .join('')
        .trim(),
    ),
  );

let model: Created;

test.beforeAll(async ({ request }) => {
  model = await createNested(request);
});

test('the server sends canonical paths and counts leaves', async () => {
  const amounts = model.fields.find((f) => f.name === 'amounts');
  expect(amounts?.path).toBe('amounts');
  expect(amounts?.fields?.map((f) => f.path)).toEqual(['amounts.total', 'amounts.currency']);
  // 5 leaves: id, number, amounts.total, amounts.currency, customer
  for (const c of Object.values(model.coverage)) expect(c.total).toBe(5);
});

for (const theme of THEMES) {
  test.describe(`real nested model (${theme})`, () => {
    test.use({ theme, viewport: { width: 1440, height: 900 } });

    test('the table shows the object with its sub-fields under it, collapsible', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(`/models/${model.id}?view=table`);
      await expect(
        page.getByRole('heading', { level: 1, name: `Order nested ${RUN}` }),
      ).toBeVisible();
      await expect(page.getByText('5 fields', { exact: true }).first()).toBeVisible();
      expect(await names(page)).toEqual([
        'id',
        'number',
        'amounts',
        'total',
        'currency',
        'customer',
      ]);
      await expect(page.getByText('amounts.total')).toBeVisible(); // the canonical path under the sub-field
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w15-real-nested-table', theme);
      await page.getByRole('button', { name: 'Collapse amounts' }).click();
      expect(await names(page)).toEqual(['id', 'number', 'amounts', 'customer']);
      await page.getByRole('button', { name: 'Expand amounts' }).click();
      expect(await names(page)).toHaveLength(6);
      // a filter keeps the parent of the match
      await page.getByRole('searchbox', { name: 'Filter fields' }).fill('currency');
      expect(await names(page)).toEqual(['amounts', 'currency']);
    });

    test('the graph draws the leaves by path; the list is indented; the detail names the path', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(`/models/${model.id}?view=graph&scope=all`);
      await expect(page.locator('.react-flow__node-canonical')).toHaveCount(5); // leaves; "amounts" only groups them
      await openControls(page);
      const row = page.getByRole('option', { name: /amounts\.total ← / }).first();
      await row.click();
      await expect(
        page
          .getByRole('region', { name: 'Mapping detail' })
          .getByRole('heading', { name: /^amounts\.total ← / }),
      ).toBeVisible();
      await expect(page).toHaveURL(/field=amounts\.total/);
      await expect(
        page.locator('.react-flow__node-canonical').filter({ hasText: 'amounts.total' }),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w15-real-nested-graph', theme);
      // a link keeps the nested selection
      await page.reload();
      await expect(
        page
          .getByRole('region', { name: 'Mapping detail' })
          .getByRole('heading', { name: /^amounts\.total ← / }),
      ).toBeVisible();
    });
  });
}
