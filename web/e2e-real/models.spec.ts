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
 * The recorded drafts come from the repo (tests/fixtures/drafts). Serial: each flow leaves its model for the next.
 *
 * Run it on a FRESH stack (down -v, up, load the fixtures): once an Order model exists for the current builds,
 * Generate answers "ready" and opens it instead of starting a session, so the generation flows are skipped or fail.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const APIS = ['test-catalog-api', 'second-catalog-api'];

const draft = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(DRAFTS, `catalog-order-${name}.json`), 'utf8'));
const auth = { Authorization: `Bearer ${TOKEN}` };
// a name per run: the same draft stored twice answers 200 and keeps the first model, so reruns need new names
const RUN = Date.now().toString(36);
const NAME = `Order ${RUN}`;

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
  // drafts are open to everyone now: no token is anonymous (404 for an unknown session), a WRONG token is a 401
  const anonymous = await request.post(`${API}/v1/models/sessions/s-none/draft`, { data: {} });
  expect(anonymous.status()).toBe(404);
  const wrong = await request.post(`${API}/v1/models/sessions/s-none/draft`, {
    headers: { Authorization: 'Bearer pl_wrong_token_value' },
    data: {},
  });
  expect(wrong.status()).toBe(401);
  // the maintainer views of the list need the token
  expect((await request.get(`${API}/v1/models?visibility=all`)).status()).toBe(401);
  expect((await request.get(`${API}/v1/models?visibility=all`, { headers: auth })).status()).toBe(
    200,
  );
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

interface Item {
  id: string;
  name: string;
  concept: string;
  visibility?: string;
  official?: boolean;
}
const list = async (request: APIRequestContext, q = '', headers: Record<string, string> = {}) =>
  ((await (await request.get(`${API}/v1/models${q}`, { headers })).json()) as { items: Item[] })
    .items;

async function goToSuggestions(page: Page) {
  await pickTwo(page);
  await page.getByRole('button', { name: 'Suggest models →' }).click();
  await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
}
const orderRow = (page: Page, idx: number) => page.locator('article.concept').nth(idx);
const generate = (page: Page, idx: number) =>
  orderRow(page, idx)
    .getByRole('button', { name: /^Generate/ })
    .first();

async function toggleDark(page: Page, name: string) {
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, name, 'dark');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
}

// ---- the flows, in order: they share one stack and each leaves its model for the next ----

test('a maintainer who generates on the server sees clearly when the server has no model key (503)', async ({
  page,
  request,
}) => {
  const probe = await request.post(`${API}/v1/models/generate`, {
    headers: auth,
    data: { apis: APIS, concept: 'order' },
  });
  test.skip(
    probe.status() !== 503,
    'this stack has a model key: server generation runs a real job',
  );
  expect((await probe.json()).error).toBe('llm_unavailable');
  const idx = await conceptIndex(request, 'order');

  await signInThenModels(page);
  await goToSuggestions(page);
  // signed in: Generate is the server action, and Claude is offered beside it
  await expect(
    orderRow(page, idx).getByRole('button', { name: 'Use Claude instead to generate Order' }),
  ).toBeVisible();
  await generate(page, idx).click();
  const alert = page.getByRole('alert').filter({ hasText: 'not configured' });
  await expect(alert).toContainText('Server-side generation is not configured on this Plume');
  await expect(alert.getByRole('button', { name: 'Use Claude instead' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Generation on the server' })).toHaveCount(0);
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-generate-503', 'light');
  await toggleDark(page, 'w12-real-generate-503');
  // the fallback opens the Claude session, which stores an UNRELEASED model for a signed-in maintainer
  await alert.getByRole('button', { name: 'Use Claude instead' }).click();
  const panel = page.getByRole('region', { name: 'Generation session' });
  await expect(panel.getByText('Stored unreleased.')).toBeVisible();
  await expect(panel.getByLabel('Command to add the maintainer connector')).not.toContainText(
    TOKEN,
  );
});

test('anonymous: Claude session, a refused draft, then an UNLISTED model with share link, owner key and lineage', async ({
  page,
  request,
}) => {
  const idx = await conceptIndex(request, 'order');
  const before = await list(request);
  await page.goto('/models');
  await goToSuggestions(page);
  await expect(
    orderRow(page, idx).getByRole('button', { name: /^Use Claude instead to generate/ }),
  ).toHaveCount(0);
  await generate(page, idx).click();
  const panel = page.getByRole('region', { name: 'Generation session' });
  await expect(panel.getByRole('heading', { name: /^Waiting for a draft/ })).toBeVisible();
  const prompt = (await panel.getByLabel('Prompt for Claude').textContent()) ?? '';
  const sessionId = /(s-[0-9a-f]+)/.exec(prompt)?.[1];
  expect(sessionId, 'the prompt names the session').toBeTruthy();
  // no maintainer token needed: the reader connector, and the model is stored unlisted
  await expect(panel.getByLabel('Command to add the Plume connector')).not.toContainText('Bearer');
  await expect(panel.getByText('Stored unlisted: only people with the link.')).toBeVisible();
  const open = (await (await request.get(`${API}/v1/models/sessions/${sessionId}`)).json()) as {
    status: string;
    snapshotId: string | null;
  };
  expect(open).toMatchObject({ status: 'open', snapshotId: null });

  // a real refusal stores nothing
  await panel.getByLabel('Draft JSON').fill(JSON.stringify(draft('bad-quote-not-in-doc')));
  await panel.getByRole('button', { name: 'Submit draft' }).click();
  await expect(panel.getByRole('alert').getByText('QUOTE_NOT_FOUND')).toBeVisible();
  await expect(panel.getByRole('alert').getByText(/the quote is not in/)).toBeVisible();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-anonymous-refused', 'light');
  expect(await list(request)).toEqual(before);

  // a good draft: stored unlisted, the page opens it
  await panel
    .getByLabel('Draft JSON')
    .fill(JSON.stringify({ ...(draft('good') as object), name: NAME }));
  await panel.getByRole('button', { name: 'Submit draft' }).click();
  await expect(page.getByRole('heading', { level: 1, name: NAME })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveURL(/\/models\/u-[A-Za-z0-9_-]+$/);
  const modelId = new URL(page.url()).pathname.split('/').pop() ?? '';
  await expect(page.locator('.chip', { hasText: 'Unlisted: anyone with the link' })).toBeVisible();
  // the owner key: shown once, saved in this browser
  const notice = page.getByText('Your model is saved, and unlisted');
  await expect(notice).toBeVisible();
  const ownerKey = await page.locator('.owner-key').textContent();
  expect(ownerKey).toBeTruthy();
  const stored = await page.evaluate(() => localStorage.getItem('plume-owner-keys'));
  expect(JSON.parse(stored ?? '[]')).toContain(ownerKey);
  // the share link is this site + the model's path; Modify with Claude carries the server's prompt
  const share = page.getByRole('region', { name: 'Share this model' });
  await expect(share.getByLabel('Link to this model')).toHaveValue(
    `${new URL(page.url()).origin}/models/${modelId}`,
  );
  const revise = page.getByRole('region', { name: 'Modify with Claude' });
  await expect(revise.getByLabel('Prompt for Claude')).toContainText(modelId);
  await expect(page.getByRole('button', { name: 'Release' })).toHaveCount(0);
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-unlisted-model', 'light');
  await toggleDark(page, 'w12-real-unlisted-model');

  // anyone with the link sees it (no token, no owner key); it is in no list
  const view = await request.get(`${API}/v1/models/${modelId}`);
  expect(view.status()).toBe(200);
  const body = (await view.json()) as { visibility: string; official: boolean };
  expect(body).toMatchObject({ visibility: 'unlisted', official: false });
  expect((await list(request)).map((m) => m.id)).not.toContain(modelId);
  const polled = (await (await request.get(`${API}/v1/models/sessions/${sessionId}`)).json()) as {
    status: string;
    snapshotId: string;
    visibility: string;
  };
  expect(polled).toMatchObject({
    status: 'submitted',
    snapshotId: modelId,
    visibility: 'unlisted',
  });

  // a second version of the same unlisted model: what "Modify with Claude" ends in
  const rev = (await (await request.post(`${API}/v1/models/${modelId}/revise`)).json()) as {
    sessionId: string;
    startingDraft: Record<string, unknown>;
  };
  const v2 = await request.post(
    `${API}/v1/models/sessions/${rev.sessionId}/draft?basedOn=${modelId}`,
    {
      data: { ...rev.startingDraft, name: `${NAME} (revised)` },
    },
  );
  expect([200, 201]).toContain(v2.status());
  const v2Id = ((await v2.json()) as { model: { id: string } }).model.id;
  expect(v2Id).not.toBe(modelId);
  await page.goto(`/models/${v2Id}`);
  await expect(page.getByRole('heading', { level: 1, name: `${NAME} (revised)` })).toBeVisible();
  await expect(page.locator('.lineage')).toContainText('v2 of 2');
  await expect(page.locator('.lineage').getByRole('link', { name: modelId })).toBeVisible();
  await page.getByText(/^Versions of this model \(2\)/).click();
  await expect(page.getByText('this version')).toBeVisible();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-lineage', 'light');
  await toggleDark(page, 'w12-real-lineage');
  await page.goto(`/models/${modelId}`);
  await expect(page.getByText('A newer version of this model exists')).toBeVisible();
  await expect(page.locator('.lineage')).toContainText('v1 of 2');

  // "Your models" lists the latest version under this browser's key; the Official list does not
  await page.goto('/models');
  const mine = page.getByRole('region', { name: 'Your models' });
  await expect(mine.getByRole('link', { name: `${NAME} (revised)` })).toBeVisible();
  await expect(mine.getByText('v2 of 2')).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Official models' }).getByText(`${NAME} (revised)`),
  ).toHaveCount(0);
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-your-models', 'light');
});

test('a maintainer reviews an UNRELEASED model: Release makes it Official, Discard removes it', async ({
  page,
  request,
}) => {
  // two unreleased models, written the way Claude does through the connector (a draft with the token)
  async function unreleased(name: string) {
    const s = (await (
      await request.post(`${API}/v1/models/generate`, {
        headers: auth,
        data: { apis: APIS, concept: 'order', engine: 'claude', force: true },
      })
    ).json()) as { sessionId: string };
    const r = await request.post(`${API}/v1/models/sessions/${s.sessionId}/draft`, {
      headers: auth,
      data: { ...(draft('good') as object), name },
    });
    expect(r.status()).toBe(201);
    const m = (await r.json()) as { visibility: string; model: { id: string } };
    expect(m.visibility).toBe('unreleased');
    return m.model.id;
  }
  const keep = await unreleased(`${NAME} (to release)`);
  const drop = await unreleased(`${NAME} (to discard)`);

  // never public
  expect((await request.get(`${API}/v1/models/${keep}`)).status()).toBe(404);
  expect((await list(request)).map((m) => m.id)).not.toContain(keep);
  expect((await list(request, '?visibility=unreleased', auth)).map((m) => m.id)).toEqual(
    expect.arrayContaining([keep, drop]),
  );

  await signInThenModels(page);
  const waiting = page.getByRole('region', { name: 'Waiting for review' });
  await expect(waiting.getByRole('link', { name: `${NAME} (to release)` })).toBeVisible();
  await expect(waiting.getByRole('link', { name: `${NAME} (to discard)` })).toBeVisible();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-waiting-for-review', 'light');

  await waiting.getByRole('link', { name: `${NAME} (to release)` }).click();
  await expect(page.getByRole('heading', { level: 1, name: `${NAME} (to release)` })).toBeVisible();
  await expect(page.getByText('Unreleased: waiting for your review')).toBeVisible();
  await expect(page.locator('.chip', { hasText: 'Unreleased' })).toBeVisible();
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-unreleased-review', 'light');
  await toggleDark(page, 'w12-real-unreleased-review');
  await page.getByRole('button', { name: 'Release' }).click();
  await expect(page.locator('.chip', { hasText: 'Official' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Release' })).toHaveCount(0);
  await expect(page.getByText('Unreleased: waiting for your review')).toHaveCount(0);
  await settle(page);
  await shot(page, 'w12-real-released', 'light');
  // now public: anyone can open it and the list shows it, with the badge
  expect((await request.get(`${API}/v1/models/${keep}`)).status()).toBe(200);
  expect((await list(request)).map((m) => m.id)).toContain(keep);
  // releasing twice is a 409 the UI explains: the page already reloaded, so ask the API directly
  expect((await request.post(`${API}/v1/models/${keep}/release`, { headers: auth })).status()).toBe(
    409,
  );

  // discard
  await page
    .getByRole('navigation', { name: 'Breadcrumb' })
    .getByRole('link', { name: 'Models' })
    .click();
  await page
    .getByRole('region', { name: 'Waiting for review' })
    .getByRole('link', { name: `${NAME} (to discard)` })
    .click();
  await expect(page.getByRole('heading', { level: 1, name: `${NAME} (to discard)` })).toBeVisible();
  await page.getByRole('button', { name: 'Discard' }).click();
  await expect(page.getByText('Discard this model? It cannot be undone.')).toBeVisible();
  await page.getByRole('button', { name: 'Yes, discard' }).click();
  await expect(page.locator('.chip', { hasText: 'Discarded' })).toBeVisible();
  // a discarded model is out of the review queue and the public list; the maintainer's "all" view marks it
  const all = await list(request, '?visibility=all', auth);
  const dropped = all.find((m) => m.id === drop);
  if (dropped) expect(dropped.visibility).toBe('discarded');
  expect((await list(request, '?visibility=unreleased', auth)).map((m) => m.id)).not.toContain(
    drop,
  );
  expect((await list(request)).map((m) => m.id)).not.toContain(drop);
  expect((await request.get(`${API}/v1/models/${drop}`)).status()).toBe(404);

  // the public list: Official only, with the badge; nothing unlisted or unreleased
  await page
    .getByRole('navigation', { name: 'Breadcrumb' })
    .getByRole('link', { name: 'Models' })
    .click();
  const official = page.getByRole('region', { name: 'Official models' });
  await expect(official.getByRole('link', { name: `${NAME} (to release)` })).toBeVisible();
  await expect(official.getByText('Official').first()).toBeVisible();
  await expect(official.getByText(`${NAME} (revised)`)).toHaveCount(0);
  await expect(official.getByText(`${NAME} (to discard)`)).toHaveCount(0);
  await settle(page);
  await expectNoSeriousA11y(page);
  await shot(page, 'w12-real-official-list', 'light');
  await toggleDark(page, 'w12-real-official-list');
});

for (const theme of THEMES) {
  test.describe(`real model view (${theme})`, () => {
    test.use({ theme });

    test('the mapping view shows the stored snapshot: nodes, edges, citations', async ({
      page,
      request,
    }) => {
      const items = await list(request, `?api=${APIS[0]}`);
      const item = items.find((m) => m.concept.toLowerCase() === 'order');
      expect(item, 'a released order model exists (created by the previous test)').toBeTruthy();
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

      // reach the model through the UI: the Models list (Official)
      await page.goto('/models');
      await page
        .getByRole('region', { name: 'Official models' })
        .getByRole('link', { name: snap.name })
        .click();
      await expect(page.getByRole('heading', { level: 1, name: snap.name })).toBeVisible();

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
