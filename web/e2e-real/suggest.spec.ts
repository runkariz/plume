import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * The suggestions page and the app pickers against the real API (W13): what the page shows is compared with what
 * POST /v1/models/suggest answers for the same query (reason, counts, filters, search, scope), and every API that
 * has a package icon shows it. Needs the stack with shopify-mini, woo-mini and mirakl-mini loaded.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const APIS = ['shopify', 'woocommerce', 'mirakl'];
const url = (q = '') => `/models/suggest?apis=${APIS.join(',')}${q}`;

interface Concept {
  id: string;
  name: string;
  reason: string;
  coverage: Record<string, string>;
  apiCounts: Record<string, { models: number; endpoints: number; fields: number }>;
}
interface Suggest {
  concepts: Concept[];
  total: number;
  counts: { all: number; inAll: number; write: number; single: number };
  apis: { id: string; logo: { url: string | null } }[];
}
async function suggest(request: APIRequestContext, body: Record<string, unknown> = {}) {
  const res = await request.post(`${API}/v1/models/suggest`, { data: { apis: APIS, ...body } });
  expect(res.status()).toBe(200);
  return (await res.json()) as Suggest;
}
const names = (r: Suggest) => r.concepts.map((c) => c.name);
const rows = (page: Page) => page.locator('article.concept h3');

test('the real API refuses a require outside the selected APIs', async ({ request }) => {
  const res = await request.post(`${API}/v1/models/suggest`, {
    data: { apis: APIS, require: ['github'] },
  });
  expect(res.status()).toBe(400);
});

for (const theme of THEMES) {
  test.describe(`real suggestions (${theme})`, () => {
    test.use({ theme });

    test('each concept shows the server\'s reason and its per-API counts, and no "documented by" line', async ({
      page,
      request,
    }) => {
      const all = await suggest(request);
      expect(all.concepts.length, 'the fixtures give at least one shared concept').toBeGreaterThan(
        0,
      );
      await page.goto(url());
      await expect(rows(page)).toHaveText(names(all));
      for (const c of all.concepts) {
        const card = page.getByRole('article', { name: c.name, exact: true });
        await expect(card.locator('.concept-reason')).toHaveText(c.reason);
        // the counts list has one line per API that has something to count
        const withCounts = APIS.filter((id) => {
          const k = c.apiCounts[id];
          return k && (k.models || k.endpoints || k.fields);
        });
        if (withCounts.length)
          await expect(
            card.getByRole('list', { name: `${c.name} in each API` }).getByRole('listitem'),
          ).toHaveCount(withCounts.length);
      }
      await expect(page.getByText(/as documented by/)).toHaveCount(0);
      // the chips carry the server's numbers
      await expect(
        page.getByRole('radio', { name: `All concepts · ${all.counts.all}` }),
      ).toBeAttached();
      await expect(
        page.getByRole('radio', { name: `Can write · ${all.counts.write}` }),
      ).toBeAttached();
      await expect(
        page.getByRole('radio', { name: `Only in one API · ${all.counts.single}` }),
      ).toBeAttached();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-real-suggest', theme);
    });

    test('search + per-API filter + chips combine, and the URL keeps them', async ({
      page,
      request,
    }) => {
      const all = await suggest(request);
      const first = all.concepts[0] as Concept;
      const present = APIS.filter((id) => first.coverage[id] !== 'absent');
      const q = first.name.toLowerCase();
      const expected = await suggest(request, { q, require: present });
      expect(names(expected)).toContain(first.name);

      await page.goto(url());
      await expect(rows(page)).toHaveText(names(all));
      await page.getByRole('searchbox', { name: 'Search concepts' }).fill(q);
      for (const id of present) {
        const label = id === 'woocommerce' ? 'WooCommerce' : id === 'mirakl' ? 'Mirakl' : 'Shopify';
        await page
          .getByRole('group', { name: 'Only concepts that exist in' })
          .getByRole('checkbox', { name: label })
          .click({ force: true });
      }
      await expect(rows(page)).toHaveText(names(expected));
      await expect(page).toHaveURL(new RegExp(`q=${encodeURIComponent(q)}`));
      await expect
        .poll(() => new URL(page.url()).searchParams.get('require'))
        .toBe(present.join(','));
      await expect(
        page.getByRole('radio', { name: `All concepts · ${expected.counts.all}` }),
      ).toBeAttached();
      // the chip "In all N APIs" narrows the same list, from the server
      const everywhere = await suggest(request, { q, require: present, inAll: true });
      await page.getByRole('radio', { name: /^In all 3 APIs/ }).click({ force: true });
      if (everywhere.concepts.length) await expect(rows(page)).toHaveText(names(everywhere));
      else await expect(page.getByText('No concepts match these filters')).toBeVisible();
      await page.getByRole('radio', { name: /^All concepts/ }).click({ force: true });
      await expect(rows(page)).toHaveText(names(expected));
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-real-suggest-filtered', theme);

      // a link with the filters opens the same view
      await page.reload();
      await expect(rows(page)).toHaveText(names(expected));
      await expect(page.getByRole('searchbox', { name: 'Search concepts' })).toHaveValue(q);
    });

    test('concepts that exist in only one API can be browsed', async ({ page, request }) => {
      const single = await suggest(request, { only: 'single' });
      expect(single.total).toBeGreaterThan(0);
      await page.goto(url());
      await page.getByRole('radio', { name: /^Only in one API/ }).click({ force: true });
      await expect(rows(page)).toHaveText(names(single));
      await expect(page).toHaveURL(/only=single/);
      await expect(page.getByRole('radio', { name: /^Can write/ })).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-real-suggest-single', theme);
    });

    test('the package icon shows wherever an API is shown (pickers, chips, coverage circles)', async ({
      page,
      request,
    }) => {
      const all = await suggest(request);
      const withIcon = all.apis.filter((a) => a.logo.url);
      const without = all.apis.filter((a) => !a.logo.url);
      expect(withIcon.length, 'the shopify and woo fixtures have icons').toBeGreaterThan(0);
      expect(without.length, 'mirakl has none: the letter shows').toBeGreaterThan(0);

      await page.goto(url());
      await expect(rows(page).first()).toBeVisible();
      const imgs = page.getByRole('list', { name: 'Selected APIs' }).locator('img');
      await expect(imgs).toHaveCount(withIcon.length);
      for (let i = 0; i < withIcon.length; i += 1) {
        const img = imgs.nth(i);
        await expect
          .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
          .toBeGreaterThan(0);
        expect((await img.boundingBox())?.width ?? 0).toBeGreaterThan(14); // loaded AND visible
      }
      await expect(
        page.locator('article.concept').first().locator('.avatar-api.icon').first(),
      ).toBeVisible();

      // the app pickers of /models
      await page.goto('/models');
      const cands = (await (await request.get(`${API}/v1/models/candidates`)).json()) as {
        items: { id: string; logo: { url: string | null } }[];
      };
      const iconIds = cands.items.filter((c) => c.logo.url).map((c) => c.id);
      await expect(page.locator('.pick-card img')).toHaveCount(iconIds.length);
      for (let i = 0; i < iconIds.length; i += 1) {
        const img = page.locator('.pick-card img').nth(i);
        await expect
          .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
          .toBeGreaterThan(0);
        expect((await img.boundingBox())?.width ?? 0).toBeGreaterThan(20);
      }
      await page.getByRole('checkbox', { name: /Shopify/ }).check({ force: true });
      // by keyboard: once something is selected the sticky selection bar can cover the last cards
      await page.getByRole('checkbox', { name: /WooCommerce/ }).focus();
      await page.keyboard.press('Space');
      await expect(page.getByRole('checkbox', { name: /WooCommerce/ })).toBeChecked();
      await expect(page.getByRole('region', { name: 'Selected APIs' }).locator('img')).toHaveCount(
        2,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w13-real-pick-apps-icons', theme);
    });
  });
}
