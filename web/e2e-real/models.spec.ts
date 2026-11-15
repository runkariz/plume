import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * Canonical models against the real API (P5): pick two loaded APIs, see the suggestions, open a generation
 * session, get a draft refused with real issue codes, let a draft arrive over HTTP (what Claude does through the
 * maintainer MCP) and watch the page open the stored model, then check the mapping graph against the snapshot.
 *
 * Needs the stack with a maintainer token and the fixtures test-catalog + second-catalog loaded (see wizard.spec.ts).
 * The recorded drafts come from the repo (tests/fixtures/drafts). Serial: one session creates the snapshot.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const APIS = ['test-catalog-api', 'second-catalog-api'];

const draft = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(DRAFTS, `catalog-order-${name}.json`), 'utf8'));
const auth = { Authorization: `Bearer ${TOKEN}` };

async function signInThenModels(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  // in-app navigation: the key lives in memory only
  await page.getByRole('link', { name: 'Models', exact: true }).click();
}

async function pickTwo(page: Page) {
  await expect(page.getByRole('checkbox', { name: /Test Catalog API/ })).toBeVisible();
  await page.getByRole('checkbox', { name: /Test Catalog API/ }).check({ force: true });
  await page.getByRole('checkbox', { name: /Second Catalog API/ }).check({ force: true });
  await expect(page.getByText('2 selected')).toBeVisible();
}

async function conceptIndex(request: APIRequestContext, id: string) {
  const res = await request.post(`${API}/v1/models/suggest`, { data: { apis: APIS } });
  const body = (await res.json()) as { concepts: { id: string }[] };
  const i = body.concepts.findIndex((c) => c.id === id);
  expect(i, `concept ${id} is suggested for the two catalogs`).toBeGreaterThanOrEqual(0);
  return i;
}

test.describe.configure({ mode: 'serial' });

test('the real reader endpoints answer for the models pages', async ({ request }) => {
  const cands = (await (await request.get(`${API}/v1/models/candidates`)).json()) as {
    items: { id: string }[];
  };
  expect(cands.items.map((a) => a.id)).toEqual(expect.arrayContaining(APIS));
  const one = await request.post(`${API}/v1/models/suggest`, {
    data: { apis: ['test-catalog-api'] },
  });
  expect(one.status()).toBe(422); // at least two APIs
  const noToken = await request.post(`${API}/v1/models/sessions/s-none/draft`, { data: {} });
  expect(noToken.status()).toBe(401);
});

test('pick apps and suggestions show the real concepts, coverage and pinned builds', async ({
  page,
  request,
}) => {
  await page.goto('/models');
  await pickTwo(page);
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w7-real-pick-apps', 'light');
  await page.getByRole('button', { name: 'Suggest models →' }).click();
  await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
  const body = (await (
    await request.post(`${API}/v1/models/suggest`, { data: { apis: APIS } })
  ).json()) as {
    concepts: { id: string }[];
  };
  await expect(page.locator('article.concept')).toHaveCount(body.concepts.length);
  await expect(page.getByRole('radio', { name: 'In all 2 APIs' })).toBeVisible();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w7-real-suggestions', 'light');
});

for (const theme of THEMES) {
  test.describe(`real generation session (${theme})`, () => {
    test.use({ theme });

    test('session waits for a draft, refuses a bad one, then notices the model Claude submits', async ({
      page,
      request,
    }) => {
      const existing = (await (await request.get(`${API}/v1/models?api=${APIS[0]}`)).json()) as {
        items: { concept: string }[];
      };
      test.skip(
        existing.items.some((m) => m.concept.toLowerCase() === 'order'),
        'an order snapshot already exists on these builds: this run exercises the "ready" path instead',
      );
      const idx = await conceptIndex(request, 'order');

      await signInThenModels(page);
      await pickTwo(page);
      await page.getByRole('button', { name: 'Suggest models →' }).click();
      await page
        .locator('article.concept')
        .nth(idx)
        .getByRole('button', { name: /^Generate/ })
        .click();

      const panel = page.getByRole('region', { name: 'Generation session' });
      await expect(panel.getByRole('heading', { name: /^Waiting for a draft/ })).toBeVisible();
      const prompt = (await panel.getByLabel('Prompt for Claude').textContent()) ?? '';
      const sessionId = /get_model_context\("(s-[0-9a-f]+)"\)/.exec(prompt)?.[1];
      expect(sessionId).toBeTruthy();
      // the copy-ready connect line carries a placeholder, never a real token
      const connect = panel.getByLabel('Command to add the maintainer connector');
      await expect(connect).toContainText('/maintainer/mcp');
      await expect(connect).not.toContainText(TOKEN);
      await expect(
        panel.getByRole('list', { name: 'Pinned builds' }).getByText(/^b-[0-9a-f]{12}$/),
      ).toHaveCount(2);
      await panel.getByRole('button', { name: 'See what Plume gives Claude' }).click();
      const pack = panel.getByRole('region', { name: 'Evidence pack' });
      await expect(pack.getByRole('region', { name: 'Evidence for Test' })).toBeVisible();
      await expect(pack.getByText('Draft format')).toBeVisible();
      // the fields come page by page: the real paged route answers, and the count matches the API's total
      await pack.getByRole('button', { name: /^Show Test fields/ }).click();
      const evidence = (await (
        await request.get(`${API}/v1/models/sessions/${sessionId}/evidence?api=${APIS[0]}`)
      ).json()) as { total_fields: number };
      await expect(
        pack
          .getByRole('region', { name: 'Evidence for Test' })
          .getByText(new RegExp(`of ${evidence.total_fields} fields shown`)),
      ).toBeVisible();

      // a real refusal: the quote is not in the cited document
      await panel.getByLabel('Draft JSON').fill(JSON.stringify(draft('bad-quote-not-in-doc')));
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(panel.getByRole('alert').getByText('QUOTE_NOT_FOUND')).toBeVisible();
      await expect(panel.getByRole('alert').getByText(/the quote is not in/)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w7-real-generate-session', theme);
      if (theme === 'light') {
        // the second run is skipped (the snapshot exists by then), so also capture the dark theme here
        await page.getByRole('button', { name: 'Switch to dark theme' }).click();
        await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
        await settle(page);
        await expectNoSeriousA11y(page);
        await shot(page, 'w7-real-generate-session', 'dark');
        await page.getByRole('button', { name: 'Switch to light theme' }).click();
      }
      const afterRefusal = (await (
        await request.get(`${API}/v1/models?api=${APIS[0]}`)
      ).json()) as { items: unknown[] };
      expect(afterRefusal.items).toHaveLength(0); // a refused draft stores nothing

      // what Claude does through the maintainer MCP, here over HTTP: the page notices and opens the model
      const created = await request.post(`${API}/v1/models/sessions/${sessionId}/draft`, {
        headers: auth,
        data: draft('good'),
      });
      expect(created.status()).toBe(201);
      await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page).toHaveURL(/\/models\/m-[0-9a-f]+$/);
    });

    test('the mapping view shows the stored snapshot: nodes, edges, citations', async ({
      page,
      request,
    }) => {
      const list = (await (await request.get(`${API}/v1/models?api=${APIS[0]}`)).json()) as {
        items: { id: string; concept: string }[];
      };
      const item = list.items.find((m) => m.concept.toLowerCase() === 'order');
      expect(item, 'the order snapshot exists (created by the previous test)').toBeTruthy();
      const snap = (await (await request.get(`${API}/v1/models/${item?.id}`)).json()) as {
        name: string;
        fields: {
          name: string;
          support: Record<string, string>;
          sources: Record<string, { paths: { path: string }[] }>;
        }[];
        inputs: { id: string }[];
        citations: { checked: number; found: number };
      };

      // reach the model through the UI: pick, suggest, Generate (the server answers "ready")
      await signInThenModels(page);
      await pickTwo(page);
      await page.getByRole('button', { name: 'Suggest models →' }).click();
      const idx = await conceptIndex(request, 'order');
      await page
        .locator('article.concept')
        .nth(idx)
        .getByRole('button', { name: /^Generate/ })
        .click();
      await expect(page.getByRole('heading', { level: 1, name: snap.name })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Generation session' })).toHaveCount(0);

      const apiNodes = new Set<string>();
      let edges = 0;
      for (const f of snap.fields)
        for (const a of snap.inputs) {
          const sup = f.support[a.id];
          if (!sup || sup === 'unsupported') continue;
          for (const p of f.sources[a.id]?.paths ?? []) {
            apiNodes.add(`${a.id}:${p.path}`);
            edges += 1;
          }
        }
      await expect(page.locator('.react-flow__node')).toHaveCount(
        snap.fields.length + apiNodes.size + snap.inputs.length,
      );
      await expect(page.locator('.react-flow__edge')).toHaveCount(edges);
      await expect(page.getByText('Generated, unverified')).toBeVisible();
      await expect(
        page.getByText(`All ${snap.citations.checked} cited paths found in the pinned builds`),
      ).toBeVisible();
      await expect(page.getByText('Open questions')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w7-real-model-view', theme);

      // the mapping list drives the detail panel (the keyboard route into the graph)
      const second = snap.fields.find((f) =>
        Object.values(f.support).some((s) => s !== 'unsupported'),
      );
      expect(second).toBeTruthy();
      await page.getByRole('combobox', { name: 'Mapping' }).selectOption({ index: 1 });
      await expect(page.getByRole('heading', { name: / ← / })).toBeVisible();
    });
  });
}

test('a bad session id and a missing snapshot show real errors', async ({ page, request }) => {
  const res = await request.get(`${API}/v1/models/sessions/s-nope/context`);
  expect(res.status()).toBe(404);
  await page.goto('/models/m-doesnotexist');
  await expect(page.getByRole('alert')).toContainText(/not found|unknown|no such/i);
});
