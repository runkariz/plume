import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, openControls, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * Model sets against the real API: a set of two models (Order, which holds an `items` array, and Product) built
 * from the two catalog packages over HTTP, with the relation Order.items -> Product proposed (not decided yet).
 * The file name sorts last: what it stores must not change what the other specs see.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const PRODUCTS = 'endpoint:GET~/api/{version}/products';
const auth = { Authorization: `Bearer ${TOKEN}` };
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as {
  fields: unknown[];
};
const RUN = Date.now().toString(36);

interface SetJson {
  id: string;
  name: string;
  visibility: string;
  members: { concept: string; modelId: string; fieldCount?: number }[];
  relations: {
    id: string;
    confirmed: boolean;
    kind: string;
    cardinality: string;
    support: Record<string, string | null>;
    editableOptions?: {
      editable: boolean;
      current: boolean;
      missing: string[];
      kind: string;
      cardinality: string;
    }[];
  }[];
  undecided: string[];
  lineage?: { version: number; versions: number; latestId: string };
}

async function quote(request: APIRequestContext, api: string, field: string): Promise<string> {
  const res = await request.get(`${API}/v1/apis/${api}/documents/${encodeURIComponent(PRODUCTS)}`);
  expect(res.status()).toBe(200);
  const doc = (await res.json()) as { fields: { name: string; description?: string | null }[] };
  const f = doc.fields.find((x) => x.name === field);
  expect(f?.description, `${api} documents ${field}`).toBeTruthy();
  return f?.description ?? '';
}

/** A set of Order and Product with the relation order-items; with the token it is stored unreleased. */
async function createSet(
  request: APIRequestContext,
  opts: { token: boolean; confirmed: boolean; name: string },
): Promise<{ set: SetJson; collection: { id: string; url: string; created: boolean } | null }> {
  const headers = opts.token ? auth : {};
  const start = (await (
    await request.post(`${API}/v1/model-sets/sessions`, {
      headers,
      data: { apis: APIS, concepts: ['Order', 'Product'] },
    })
  ).json()) as {
    setSessionId: string;
    memberSessions: Record<string, string>;
    inputs: { api: string }[];
  };
  const cite = async (field: string) =>
    Object.fromEntries(
      await Promise.all(
        APIS.map(async (api) => [
          api,
          {
            paths: [{ path: field }],
            evidence: [{ doc_id: PRODUCTS, quote: await quote(request, api, field) }],
          },
        ]),
      ),
    );
  const order = {
    ...good,
    name: `Order ${opts.name}`,
    fields: [
      ...good.fields,
      {
        name: 'items',
        type: 'array',
        description: 'Products of the order.',
        fields: [{ name: 'id', type: 'string', sources: await cite('items[].id') }],
      },
    ],
  };
  const product = {
    name: `Product ${opts.name}`,
    fields: [
      { name: 'id', type: 'string', sources: await cite('items[].id') },
      { name: 'name', type: 'string', sources: await cite('items[].name') },
    ],
  };
  const ids: Record<string, string> = {};
  for (const [concept, draft] of [
    ['Order', order],
    ['Product', product],
  ] as const) {
    const sid = start.memberSessions[concept];
    const r = await request.post(`${API}/v1/models/sessions/${sid}/draft`, {
      headers,
      data: draft,
    });
    expect(r.status(), await r.text()).toBe(201);
    ids[concept] = ((await r.json()) as { model: { id: string } }).model.id;
  }
  const relation = {
    id: 'order-items',
    from: 'Order',
    to: 'Product',
    kind: 'embedded',
    cardinality: '1:n',
    embed: { field: 'items' },
    confirmed: opts.confirmed,
    sources: Object.fromEntries(
      await Promise.all(
        APIS.map(async (api) => [
          api,
          {
            as: 'nested',
            paths: ['items[].id'],
            evidence: [{ doc_id: PRODUCTS, quote: await quote(request, api, 'items[].id') }],
          },
        ]),
      ),
    ),
  };
  const res = await request.post(`${API}/v1/model-sets/sessions/${start.setSessionId}/draft`, {
    headers,
    data: { name: opts.name, members: ids, relations: [relation] },
  });
  expect(res.status(), await res.text()).toBe(201);
  const body = (await res.json()) as {
    set: SetJson;
    collection?: { id: string; url: string; created: boolean } | null;
  };
  return { set: body.set, collection: body.collection ?? null };
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

let proposal: SetJson;

test.beforeAll(async ({ request }) => {
  proposal = (await createSet(request, { token: true, confirmed: false, name: `Shop ${RUN}` })).set;
});

test('the server sends the shapes the diagram needs', async () => {
  expect(proposal.visibility).toBe('unreleased');
  expect(proposal.members.map((m) => m.concept)).toEqual(['Order', 'Product']);
  expect(proposal.undecided).toEqual(['order-items']);
  const rel = proposal.relations[0];
  expect(rel).toMatchObject({ kind: 'embedded', cardinality: '1:n', confirmed: false });
  expect(Object.keys(rel?.support ?? {}).sort()).toEqual([...APIS].sort());
  expect(rel?.editableOptions?.some((o) => o.editable && o.current)).toBe(true);
  expect(rel?.editableOptions?.some((o) => !o.editable && o.missing.length > 0)).toBe(true);
});

for (const theme of THEMES) {
  test.describe(`real model set (${theme})`, () => {
    test.use({ theme, viewport: { width: 1440, height: 900 } });

    test('the diagram, the list, a relation with its real sources and designs', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(`/model-sets/${proposal.id}`);
      await expect(page.getByRole('heading', { level: 1, name: `Shop ${RUN}` })).toBeVisible();
      await expect(page.getByText('1 to decide').first()).toBeVisible();
      await expect(page.locator('.react-flow__node-member')).toHaveCount(2);
      // release is blocked until the relation is decided, and the page says which one
      await expect(page.getByRole('button', { name: 'Release' })).toBeDisabled();
      await expect(
        page.getByText(/Release is blocked: 1 relation is not decided yet/),
      ).toBeVisible();
      await openControls(page, /Filter models and relations/);
      const list = page.getByRole('listbox', { name: 'Models and relations' });
      await expect(list.getByRole('option')).toHaveCount(3); // two models and one relation
      await list.getByRole('option', { name: /Order → Product/ }).click();
      const detail = page.getByRole('region', { name: 'Selected model or relation' });
      await expect(detail.getByRole('heading', { name: 'Order → Product' })).toBeVisible();
      await expect(detail.getByText('Proposal: to decide')).toBeVisible();
      // each API's source, with a quote that comes from its own package
      const sources = detail.getByRole('list', { name: 'Sources' });
      await expect(sources.getByText('items[].id').first()).toBeVisible();
      await expect(sources.getByText('as nested objects')).toHaveCount(2);
      await expect(sources.locator('blockquote')).toHaveCount(2);
      // the designs: the server's editable flags and reasons
      const radios = detail.getByRole('radio');
      const options = proposal.relations[0]?.editableOptions ?? [];
      await expect(radios).toHaveCount(options.length);
      for (const [i, o] of options.entries()) {
        if (o.editable) await expect(radios.nth(i)).toBeEnabled();
        else {
          await expect(radios.nth(i)).toBeDisabled();
          await expect(
            detail.getByText(o.missing[0] ?? '', { exact: false }).first(),
          ).toBeVisible();
        }
      }
      await expect(page).toHaveURL(/sel=r%3Aorder-items|sel=r:order-items/);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w16-real-set-relation', theme);
      // a model: its coverage and the way into its field mapping
      await list
        .getByRole('option', { name: /^Order /, exact: false })
        .first()
        .click();
      await expect(detail.getByRole('link', { name: 'Open the field mapping' })).toHaveAttribute(
        'href',
        /\/models\/m-/,
      );
      await shot(page, 'w16-real-set-model', theme);
    });
  });
}

test('decide the relation: a new version, then release makes the set and its models official', async ({
  page,
  request,
}) => {
  await signIn(page);
  await page.goto(`/model-sets/${proposal.id}?sel=r:order-items`);
  const detail = page.getByRole('region', { name: 'Selected model or relation' });
  const current =
    proposal.relations[0]?.editableOptions?.findIndex((o) => o.editable && o.current) ?? 0;
  await detail.getByRole('radio').nth(current).click();
  const bar = page.getByRole('region', { name: 'Changes to save' });
  await expect(bar).toContainText('a new unreleased version');
  await bar.getByRole('button', { name: 'Save as a new version' }).click();
  await expect(page.getByText('Saved as a new version')).toBeVisible();
  // version 2 of the same lineage, nothing left to decide
  const v2 = page.url().split('/model-sets/')[1]?.split('?')[0] ?? '';
  expect(v2).not.toBe(proposal.id);
  const v2Json = (await (
    await request.get(`${API}/v1/model-sets/${v2}`, { headers: auth })
  ).json()) as SetJson;
  expect(v2Json.undecided).toEqual([]);
  expect(v2Json.lineage).toMatchObject({ version: 2, versions: 2 });
  // the old version says a newer one exists, and cannot be edited
  await page.goto(`/model-sets/${proposal.id}?sel=r:order-items`);
  await expect(page.getByText('A newer version of this model set exists')).toBeVisible();
  for (const r of await page.getByRole('radio').all()) await expect(r).toBeDisabled();
  // release the new version
  await page.goto(`/model-sets/${v2}`);
  await expect(page.getByRole('button', { name: 'Release' })).toBeEnabled();
  await page.getByRole('button', { name: 'Release' }).click();
  await expect(page.getByText('Released: the set is Official')).toBeVisible();
  const memberLinks = page
    .getByText('These models were released with it:')
    .locator('..')
    .getByRole('link');
  await expect(memberLinks).toHaveCount(2);
  // official for everyone now: the public API serves the set and its models
  const pub = await request.get(`${API}/v1/model-sets/${v2}`);
  expect(pub.status()).toBe(200);
  expect(((await pub.json()) as SetJson).visibility).toBe('official');
  for (const m of proposal.members)
    expect((await request.get(`${API}/v1/models/${m.modelId}`)).status()).toBe(200);
  const listed = (await (await request.get(`${API}/v1/model-sets`)).json()) as {
    items: { id: string }[];
  };
  expect(listed.items.map((i) => i.id)).toContain(v2);
  await page.goto('/models');
  await expect(
    page
      .getByRole('region', { name: 'Official model sets' })
      .getByRole('link', { name: `Shop ${RUN}` }),
  ).toBeVisible();
  await shot(page, 'w16-real-set-released', 'light');
});

test('anonymous: a set made without the token is unlisted, and confirming its relation adds a version to it', async ({
  page,
  request,
}) => {
  const { set, collection } = await createSet(request, {
    token: false,
    confirmed: false,
    name: `Mine ${RUN}`,
  });
  expect(set.visibility).toBe('unlisted');
  expect(collection?.id).toMatch(/^c-/); // an anonymous save answers the My models link, not a key
  await page.goto(`/model-sets/${set.id}?sel=r:order-items`);
  await expect(page.getByRole('heading', { level: 1, name: `Mine ${RUN}` })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Share this model set' })).toBeVisible();
  const detail = page.getByRole('region', { name: 'Selected model or relation' });
  const current = set.relations[0]?.editableOptions?.findIndex((o) => o.editable && o.current) ?? 0;
  await detail.getByRole('radio').nth(current).click();
  const bar = page.getByRole('region', { name: 'Changes to save' });
  await expect(bar).toContainText('a new version of this unlisted set');
  await bar.getByRole('button', { name: 'Save as a new version' }).click();
  await expect(page.getByText('Saved as a new version')).toBeVisible();
  // this browser holds no My models link (the set was made over HTTP by someone else): it must never keep the author's
  // link, even if the server answers it for a new version (it must be a link this browser made or sent)
  const kept = await page.evaluate(() => localStorage.getItem('plume-collection'));
  expect(kept === null || kept !== collection?.id).toBe(true);
  await expect(page.getByText(/v2 of 2/).first()).toBeVisible();
  // anyone with the link sees it; it is in no public list
  const id2 = page.url().split('/model-sets/')[1]?.split('?')[0] ?? '';
  expect((await request.get(`${API}/v1/model-sets/${id2}`)).status()).toBe(200);
  const listed = (await (await request.get(`${API}/v1/model-sets`)).json()) as {
    items: { id: string }[];
  };
  expect(listed.items.map((i) => i.id)).not.toContain(id2);
});
