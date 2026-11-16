import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * What users see of release notes, against the real API with the release-notes test kit (SYNTHETIC woocommerce data:
 * `test-packages/base`, then `A-docs-changes`, loaded as API `woocommerce-test`), and the real Amazon vendor package
 * for the Sources line. Skipped unless PLUME_E2E_KIT=true (see web/README.md).
 */
const KIT = process.env.PLUME_E2E_KIT === 'true';
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ID = 'woocommerce-test';
const AMAZON = 'amazon-sp-api-vendor';

test.skip(!KIT, 'needs the test kit and the Amazon package loaded: PLUME_E2E_KIT=true');

interface Totals {
  confirmed: number;
  likely: number;
  breaking: number;
  wordingOnly: number;
  byKind: Record<string, number>;
}

for (const theme of THEMES) {
  test.describe(`what changed, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the home card says what the server says and leads to the Changes tab', async ({
      page,
      request,
    }) => {
      const list = (await (await request.get(`${API}/v1/apis`)).json()) as {
        items: {
          id: string;
          docsUpdated: { confirmed: number; likely: number; breaking: number; at: string } | null;
        }[];
      };
      const d = list.items.find((a) => a.id === ID)?.docsUpdated;
      expect(d, 'docsUpdated on the kit API').toBeTruthy();
      await page.goto('/');
      const card = page.locator('.api-card').filter({ has: page.locator(`a[href="/apis/${ID}"]`) });
      const n = (d?.confirmed ?? 0) + (d?.likely ?? 0);
      const badge = card.getByRole('link', { name: /^↻|^⚠|Docs updated/ });
      await expect(badge).toContainText(`${n} ${n === 1 ? 'change' : 'changes'}`);
      if ((d?.breaking ?? 0) > 0) await expect(badge).toContainText(`${d?.breaking} breaking`);
      // an API without notes has no badge
      await expect(
        page.locator('.api-card').filter({ has: page.locator('a[href="/apis/mirakl"]') }),
      ).not.toContainText('Docs updated');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w25-real-home-badge', theme);
      await badge.click();
      await expect(page.getByRole('region', { name: /^Changes of / })).toBeVisible();
    });

    test("the Changes tab: the server's builds, counts, items, quotes and links", async ({
      page,
      request,
    }) => {
      const totals = (
        (await (
          await request.get(`${API}/v1/apis/${ID}/changes?wordingOnly=false&limit=1`)
        ).json()) as {
          totals: Totals;
        }
      ).totals;
      const wording = (
        (await (await request.get(`${API}/v1/apis/${ID}/changes/timeline`)).json()) as {
          items: { counts: { wordingOnly: number } }[];
        }
      ).items[0]?.counts.wordingOnly as number;
      const all = (await (
        await request.get(`${API}/v1/apis/${ID}/changes?wordingOnly=false&limit=200`)
      ).json()) as {
        items: {
          id: string;
          breaking: boolean;
          quote: string | null;
          vendorUrl: string | null;
          removedDocument?: boolean;
        }[];
      };
      await page.goto(`/apis/${ID}?section=changes`);
      const panel = page.getByRole('region', { name: /^Changes of / });
      await expect(panel).toBeVisible({ timeout: 30_000 });
      const timeline = page.getByRole('list', { name: 'Builds' });
      await expect(timeline.getByRole('listitem')).toHaveCount(1);
      await expect(timeline).toContainText('latest');
      await expect(timeline).toContainText('Breaking');
      // the chips show the server's own counts
      const chip = (re: RegExp) => panel.locator('.pills label').filter({ hasText: re });
      await expect(chip(/^All/)).toContainText(String(totals.confirmed + totals.likely));
      await expect(chip(/^Breaking/)).toContainText(String(totals.breaking));
      await expect(chip(/^Endpoints/)).toContainText(String(totals.byKind.endpoint ?? 0));
      // every item is listed, as text, with its vendor page (http(s))
      await expect(panel.getByRole('listitem')).toHaveCount(all.items.length);
      for (const i of all.items.filter((x) => x.quote).slice(0, 3))
        await expect(panel).toContainText((i.quote ?? '').slice(0, 30));
      for (const link of await panel.getByRole('link', { name: 'Vendor page' }).all())
        expect(await link.getAttribute('href')).toMatch(/^https:\/\/developer\.woocommerce\.com\//);
      // a removed endpoint has no document to open in Plume any more
      const removed = panel.getByRole('listitem').filter({ hasText: 'removed' }).first();
      await expect(removed).toBeVisible();
      await expect(removed.getByRole('link', { name: 'Open in Plume' })).toHaveCount(0);
      // wording is kept apart and one click away
      await expect(panel).toContainText(`Wording only: ${wording} description`);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('region', { name: 'Builds with changes' }),
        'w25-real-changes-timeline',
        theme,
      );
      await shotOf(panel, 'w25-real-changes-list', theme);
      // filters: Breaking asks the server; Fields (a group) is filtered here
      await chip(/^Breaking/).click();
      await expect(panel.getByRole('listitem')).toHaveCount(totals.breaking);
      await expect(page).toHaveURL(/filter=breaking/);
      await chip(/^Fields/).click();
      await expect(panel.getByRole('listitem')).toHaveCount(
        (totals.byKind.param ?? 0) +
          (totals.byKind.property ?? 0) +
          (totals.byKind.request_field ?? 0) +
          (totals.byKind.response_field ?? 0),
      );
      await chip(/^Wording only/).click();
      await expect(panel.getByRole('listitem')).toHaveCount(wording);
      await expect(panel).toContainText('Note the customer left');
      await shotOf(panel, 'w25-real-changes-wording', theme);
    });

    test('the Atom link serves a feed of plain text', async ({ page, request }) => {
      await page.goto(`/apis/${ID}?section=changes`);
      const href = await page.getByRole('link', { name: 'Subscribe (Atom)' }).getAttribute('href');
      expect(href).toBe(`${API}/v1/apis/${ID}/changes.atom`);
      const res = await request.get(href ?? '');
      expect(res.status()).toBe(200);
      expect(res.headers()['content-type']).toContain('application/atom+xml');
      expect(await res.text()).toContain('<feed');
    });
  });
}

test('a model without an impact from the server shows no impact banner (feature detection)', async ({
  page,
  request,
}) => {
  const models = (await (await request.get(`${API}/v1/models`)).json()) as {
    items: { id: string; impact?: unknown }[];
  };
  await page.goto('/models');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  for (const m of models.items.filter((x) => !x.impact)) {
    await page.goto(`/models/${m.id}`);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByTestId('impact-banner')).toHaveCount(0);
  }
});

for (const theme of THEMES) {
  test.describe(`many sources, real Amazon package (${theme})`, () => {
    test.use({ theme });
    test('one compact line, a disclosure with file names, the host alias collapsed', async ({
      page,
      request,
    }) => {
      const d = (await (await request.get(`${API}/v1/apis/${AMAZON}`)).json()) as {
        sources: { url: string; kind: string }[];
        extractedAt: string | null;
      };
      const specs = d.sources.filter((s) => s.kind === 'spec');
      expect(specs.length).toBeGreaterThan(5);
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(`/apis/${AMAZON}`);
      const line = page.getByTestId('sources-line');
      await expect(line).toContainText(`${specs.length} OpenAPI specs`);
      await expect(line).toContainText('Extracted');
      await expect(line).not.toContainText('from docs');
      // the changelog linked on two hosts is one entry
      const changelogs = d.sources.filter((s) => s.kind === 'changelog');
      expect(changelogs.length).toBe(2);
      await expect(line).not.toContainText('2 changelogs');
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.titlerow'), 'w25-real-amazon-sources', theme);
      await page.getByText(/^All sources \(/).click();
      const detail = page.getByTestId('sources-detail');
      await expect(detail.getByRole('link', { name: 'vendorOrders.json' })).toBeVisible();
      await expect(detail.getByRole('listitem')).toHaveCount(d.sources.length - 1);
      await expect(detail).toContainText('also linked as developer-docs.amazon');
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('.titlerow'), 'w25-real-amazon-sources-open', theme);
      // phone width: the header does not push the page sideways
      await page.setViewportSize({ width: 375, height: 900 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
      ).toBe(false);
      await shotOf(page.locator('.titlerow'), 'w25-real-amazon-sources-375', theme);
    });
  });
}
