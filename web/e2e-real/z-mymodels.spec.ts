import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shot, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * "My models" against the real API: an anonymous save answers a `collection` (the link), later saves send it and join
 * it, the link lists the models, a second link merges into the first, and a mistyped link is refused. The server no
 * longer issues owner keys, so the transition from keys is covered by the mock specs and the backend's own tests.
 * The file name sorts late: the models it stores must not change what the other specs see.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as object;
const RUN = Date.now().toString(36);

interface Ref {
  id: string;
  url: string;
  created: boolean;
  note?: string | null;
}

/** An anonymous Order (a new lineage). With `collection` it joins that link; without, the server starts a new one. */
async function save(
  request: APIRequestContext,
  name: string,
  collection?: string,
): Promise<{ id: string; collection: Ref; raw: Record<string, unknown> }> {
  const started = (await (
    await request.post(`${API}/v1/models/generate`, {
      data: { apis: APIS, concept: 'Order', engine: 'claude', force: true },
    })
  ).json()) as { sessionId: string };
  const q = collection ? `?collection=${encodeURIComponent(collection)}` : '';
  const res = await request.post(`${API}/v1/models/sessions/${started.sessionId}/draft${q}`, {
    data: { ...good, name },
  });
  expect(res.status(), await res.text()).toBe(201);
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    id: (raw.model as { id: string }).id,
    collection: raw.collection as Ref,
    raw,
  };
}

const holds = (page: Page, id: string) =>
  page.addInitScript((v) => localStorage.setItem('plume-collection', v), id);

for (const theme of THEMES) {
  test.describe(`My models, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('an anonymous save answers a link (no owner key), the link lists it, and a mistyped one is refused', async ({
      page,
      request,
    }) => {
      const a = await save(request, `Order mine ${RUN}-${theme}`);
      expect(a.collection.created).toBe(true);
      expect(a.collection.id).toMatch(/^c-/);
      expect(a.collection.url).toContain(`/mine/${a.collection.id}`);
      expect(a.raw).not.toHaveProperty('ownerKey');
      // a second save that sends the link joins it, and says it is the same link
      const b = await save(request, `Order mine 2 ${RUN}-${theme}`, a.collection.id);
      expect(b.collection).toMatchObject({ id: a.collection.id, created: false });
      // an unknown link: a new one, and the server says why
      const stray = await save(request, `Order stray ${RUN}-${theme}`, 'c-NobodyHasThisLink012345');
      expect(stray.collection.created).toBe(true);
      expect(stray.collection.note).toBeTruthy();
      // the server's own list
      const list = (await (
        await request.get(`${API}/v1/collections/${a.collection.id}`)
      ).json()) as {
        count: number;
        models: { id: string }[];
        mergedInto: string | null;
      };
      expect(list.models.map((m) => m.id).sort()).toEqual([a.id, b.id].sort());
      expect(list.mergedInto).toBeNull();

      await page.goto('/models');
      const region = page.getByRole('region', { name: 'Open a My models link' });
      await region.getByText(/Have a My models link/).click();
      await region.getByLabel('My models link').fill('c-NobodyHasThisLink012345');
      await region.getByRole('button', { name: 'Open link' }).click();
      await expect(region.getByRole('alert')).toContainText('does not know that link');
      await region
        .getByLabel('My models link')
        .fill(`${new URL(page.url()).origin}/mine/${a.collection.id}`);
      await region.getByRole('button', { name: 'Open link' }).click();
      await expect(region.getByRole('status')).toContainText('Opened: 2 items');
      const mine = page.getByRole('region', { name: 'Your models' });
      await expect(mine.getByRole('link', { name: `Order mine 2 ${RUN}-${theme}` })).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(
        a.collection.id,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(mine, 'w21-real-your-models', theme);
    });

    test("the My models page, and merging this browser's other link into it", async ({
      page,
      request,
    }) => {
      const a = await save(request, `Order link A ${RUN}-${theme}`);
      const b = await save(request, `Order link B ${RUN}-${theme}`); // another person's link (a new one)
      expect(b.collection.id).not.toBe(a.collection.id);
      await holds(page, a.collection.id);
      await page.goto(`/mine/${b.collection.id}`);
      await expect(page.getByRole('heading', { level: 1, name: 'My models' })).toBeVisible();
      await expect(
        page.getByRole('region', { name: 'Models' }).getByText(`Order link B ${RUN}-${theme}`),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w21-real-mine-page', theme);
      await page.getByRole('button', { name: 'Merge my other link into this one' }).click();
      await expect(
        page.getByText(/Merged: everything from your other link is here now/),
      ).toBeVisible();
      const models = page.getByRole('region', { name: 'Models' });
      await expect(models.getByText(`Order link A ${RUN}-${theme}`)).toBeVisible();
      await expect(models.getByText(`Order link B ${RUN}-${theme}`)).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(
        b.collection.id,
      );
      // the old link is emptied and points to the new one
      const old = (await (
        await request.get(`${API}/v1/collections/${a.collection.id}`)
      ).json()) as {
        mergedInto: string | null;
        models: unknown[];
      };
      expect(old).toMatchObject({ mergedInto: b.collection.id, models: [] });
      await page.goto(`/mine/${a.collection.id}`);
      await expect(page.getByText('This link was merged into another one')).toBeVisible();
      await expect(
        page.getByRole('link', { name: 'open the one they are in now' }),
      ).toHaveAttribute('href', `/mine/${b.collection.id}`);
      await shot(page, 'w21-real-mine-merged', theme);
    });
  });
}

test('a pasted draft in the browser starts the link it shows once, and the server holds the model under it', async ({
  page,
  request,
}) => {
  // an official model of a concept turns Generate into "ready" (it opens the model, no session): use a concept that has
  // none yet. A fresh stack has one; on a used one this is skipped, not failed.
  let panel = page.getByRole('region', { name: 'Generation session' });
  let found = false;
  for (const concept of ['Product', 'Order']) {
    await page.goto('/models');
    await page.getByRole('checkbox', { name: /Test Catalog API/ }).check({ force: true });
    await page.getByRole('checkbox', { name: /Second Catalog API/ }).check({ force: true });
    await page.getByRole('button', { name: 'Suggest models →' }).click();
    await page.getByRole('button', { name: `Generate ${concept}`, exact: true }).click();
    panel = page.getByRole('region', { name: 'Generation session' });
    found = await panel
      .waitFor({ state: 'visible', timeout: 4000 })
      .then(() => true)
      .catch(() => false);
    if (found) break;
  }
  test.skip(!found, 'every concept already has an official model: run on a fresh stack');
  await panel
    .getByLabel('Draft JSON')
    .fill(JSON.stringify({ ...(good as object), name: `Order pasted ${RUN}` }));
  await panel.getByRole('button', { name: 'Submit draft' }).click();
  await expect(page.getByRole('heading', { level: 1, name: `Order pasted ${RUN}` })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText('Your model is saved, and unlisted')).toBeVisible();
  const link = await page.getByLabel('Link to My models').inputValue();
  const id = /\/mine\/(c-[A-Za-z0-9_-]+)$/.exec(link)?.[1] ?? '';
  expect(id).toBeTruthy();
  expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(id);
  const held = (await (await request.get(`${API}/v1/collections/${id}`)).json()) as {
    models: { name: string }[];
  };
  expect(held.models.map((m) => m.name)).toContain(`Order pasted ${RUN}`);
});

test.describe('a blocked API (the browser refuses every request: net::ERR_BLOCKED_BY_CLIENT)', () => {
  test('opening a link says so, and the panel stays open with what was typed', async ({
    page,
    context,
  }) => {
    await context.route('**/v1/**', (route) => route.abort('blockedbyclient'));
    await page.goto('/models');
    await expect(page.getByText('Could not load APIs')).toBeVisible();
    const region = page.getByRole('region', { name: 'Open a My models link' });
    await region.getByText(/Have a My models link/).click();
    await region.getByLabel('My models link').fill('c-SomeLinkThatIsTyped01234');
    await region.getByRole('button', { name: 'Open link' }).click();
    await expect(region.getByRole('alert')).toContainText('Could not reach the Plume API');
    await expect(region.getByLabel('My models link')).toHaveValue('c-SomeLinkThatIsTyped01234');
    expect(await region.locator('details').getAttribute('open')).not.toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBeNull();
  });
});
