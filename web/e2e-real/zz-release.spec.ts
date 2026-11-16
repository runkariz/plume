import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The maintainer's release review against the real API with REAL data: two builds of the frozen Shopify packages
 * (v12-extras, then v12b-extras: 3,226 changes, 240 suspect, none visible to users), the second tagged `latest` with
 * `plume tag --force` (its eval gate failed, as a publish would have been forced). Skipped unless
 * PLUME_E2E_RELEASE_NOTES=true after loading those packages (see web/README.md).
 */
const ENABLED = process.env.PLUME_E2E_RELEASE_NOTES === 'true';
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const auth = { Authorization: `Bearer ${TOKEN}` };
const APIID = 'shopify';

test.skip(!ENABLED, 'needs the frozen Shopify packages loaded: PLUME_E2E_RELEASE_NOTES=true');

interface Summary {
  from: string;
  to: string;
  review: string;
  tagged: boolean;
  needsAttention: boolean;
  counts: Record<string, number>;
}

async function timeline(request: APIRequestContext): Promise<Summary[]> {
  const r = await request.get(`${API}/v1/apis/${APIID}/release-notes`, { headers: auth });
  return ((await r.json()) as { items: Summary[] }).items;
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`release review, real data (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test("the maintainer home flags it; the review shows the server's numbers, the report by rule, paged", async ({
      page,
      request,
    }) => {
      const tl = await timeline(request);
      const tagged = tl.find((b) => b.tagged);
      expect(tagged, 'a tagged build with notes').toBeTruthy();
      const buildId = tagged?.to ?? '';
      const notes = (await (
        await request.get(`${API}/v1/apis/${APIID}/builds/${buildId}/release-notes`, {
          headers: auth,
        })
      ).json()) as {
        review: 'pending' | 'kept' | 'rolled_back';
        attentionReason: string;
        counts: Record<string, number>;
        report: {
          title: string;
          count: number;
          items: { id: string; subject: { fieldPath?: string; model?: string } }[];
        }[];
      };

      await signIn(page);
      const row = page.locator('.m-row').filter({ hasText: 'Shopify' });
      // the home flags a review that is still pending (a kept build is not flagged again)
      if (notes.review === 'pending') await expect(row.getByText('Needs attention')).toBeVisible();
      else await expect(row.getByText('Needs attention')).toHaveCount(0);
      await row.getByRole('link', { name: 'Release review' }).click();
      await expect(
        page.getByRole('heading', { level: 1, name: 'Release review: shopify' }),
      ).toBeVisible({
        timeout: 30_000,
      });
      // status, and the server's own reason (nothing is held)
      const label = { pending: 'Pending review', kept: 'Kept', rolled_back: 'Rolled back' }[
        notes.review
      ];
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Latest', { exact: true })).toBeVisible();
      await expect(page.getByText(notes.attentionReason, { exact: false }).first()).toBeVisible();
      const counts = page.getByRole('region', { name: 'What changed' });
      await expect(counts).toContainText(`${notes.counts.suspect} suspect`);
      await expect(counts).toContainText(`${notes.counts.unknown} without source evidence`);
      await expect(counts).toContainText('0 confirmed in the docs');
      // the report: a group per rule with the server's title, 50 at a time
      for (const g of notes.report)
        await expect(page.getByRole('region', { name: g.title, exact: true })).toBeVisible();
      const biggest = notes.report.reduce((a, b) => (b.count > a.count ? b : a));
      expect(biggest.items.length).toBe(50); // the notes carry only the first 50 of a group
      const group = page.getByRole('region', { name: biggest.title, exact: true });
      await expect(group.getByRole('listitem')).toHaveCount(50);
      await expect(
        group.getByRole('button', { name: `Show 50 more (${biggest.count - 50} left)` }),
      ).toBeVisible();
      // the next 50 come from the server's report route
      await group.getByRole('button', { name: /^Show 50 more/ }).click();
      await expect(group.getByRole('listitem')).toHaveCount(100);
      // users see nothing for this build
      await expect(
        page.getByText('No confirmed or likely changes: users see nothing new for this build.'),
      ).toBeVisible();
      // the filter searches what is loaded and offers to load the rest of the group to search it too
      const first = biggest.items[0]?.subject;
      const target = first?.fieldPath ?? first?.model ?? '';
      expect(target).not.toBe('');
      await page.getByLabel(/Filter the changes below/).fill(target);
      const loadRest = group.getByRole('button', {
        name: /^Load the other \d+ to search them too$/,
      });
      await expect(group.getByRole('status')).toContainText('loaded match');
      await loadRest.click();
      await expect(group.getByRole('status')).toContainText(`of ${biggest.count} loaded match`);
      await page.getByLabel(/Filter the changes below/).fill('');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('region', { name: 'What changed' }),
        `w22-real-what-changed`,
        theme,
      );
      await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-real-review', theme);
      await shotOf(group.getByRole('listitem').first(), 'w22-real-report-item', theme);
      await shotOf(page.locator('.release-report > p').first(), 'w22-real-report-intro', theme);
    });
  });
}

test("Copy issues and Download are the server's own text, byte for byte", async ({
  page,
  context,
  request,
}) => {
  const tl = await timeline(request);
  const buildId = tl.find((b) => b.tagged)?.to ?? '';
  const text = await (
    await request.get(
      `${API}/v1/apis/${APIID}/builds/${buildId}/release-notes/issues?format=markdown`,
      { headers: auth },
    )
  ).text();
  expect(text.length).toBeGreaterThan(200);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await signIn(page);
  await page.goto(`/maintainer/apis/${APIID}/builds/${buildId}/notes`);
  await expect(
    page.getByRole('heading', { level: 1, name: 'Release review: shopify' }),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Copy issues' }).click();
  await expect(page.getByText('Issues copied: paste them to stream')).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(text);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download issues (.md)' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe(`${APIID}-${buildId}-issues.md`);
  const path = await download.path();
  expect(readFileSync(path, 'utf8')).toBe(text);
});

test('a quote that is not in the source is refused by the server and the change keeps its class', async ({
  page,
  request,
}) => {
  const tl = await timeline(request);
  const buildId = tl.find((b) => b.tagged)?.to ?? '';
  await signIn(page);
  await page.goto(`/maintainer/apis/${APIID}/builds/${buildId}/notes`);
  // whichever group the server reports first (the groups depend on the data)
  const notes = (await (
    await request.get(`${API}/v1/apis/${APIID}/builds/${buildId}/release-notes`, { headers: auth })
  ).json()) as { report: { title: string }[] };
  const title = notes.report[0]?.title ?? '';
  expect(title).not.toBe('');
  const group = page.getByRole('region', { name: title, exact: true });
  await expect(group).toBeVisible({ timeout: 30_000 });
  const row = group.getByRole('listitem').first();
  const classChip = (await row.locator('.chip').first().innerText()).trim();
  await row.getByRole('button', { name: 'Promote to confirmed…' }).click();
  await row
    .getByLabel(/A quote from the vendor docs/)
    .fill('This sentence is certainly not in any Shopify page.');
  await row.getByRole('button', { name: 'Promote to confirmed', exact: true }).click();
  await expect(row.getByRole('alert')).toContainText('not in the source text of this build');
  await expect(row.locator('.chip').first()).toHaveText(classChip);
});

test('roll back needs a reason and moves latest back on the server; Roll forward undoes it', async ({
  page,
  request,
}) => {
  const before = await timeline(request);
  const tagged = before.find((b) => b.tagged);
  expect(tagged).toBeTruthy();
  const buildId = tagged?.to ?? '';
  const base = tagged?.from ?? '';
  await signIn(page);
  await page.goto(`/maintainer/apis/${APIID}/builds/${buildId}/notes`);
  await expect(
    page.getByRole('heading', { level: 1, name: 'Release review: shopify' }),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Roll back…' }).click();
  const dialog = page.getByRole('group', { name: 'Roll back this build' });
  await expect(dialog.getByRole('button', { name: 'Roll back', exact: true })).toBeDisabled();
  await dialog.getByLabel(/Reason/).fill('240 suspect removals: the extractor, not the docs');
  await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-real-rollback-confirm', 'light');
  await dialog.getByRole('button', { name: 'Roll back', exact: true }).click();
  await expect(page.getByText(/Rolled back: `latest` is /)).toBeVisible();
  await expect(page.getByText('Not latest')).toBeVisible();
  // the SERVER moved the tag back, and kept the build
  const after = await timeline(request);
  expect(after.find((b) => b.to === buildId)).toMatchObject({
    tagged: false,
    review: 'rolled_back',
  });
  await shotOf(page.getByRole('region', { name: 'Review' }), 'w22-real-rolled-back', 'light');
  // undo: roll forward
  await page.getByRole('button', { name: 'Roll forward' }).click();
  await expect(page.getByText('Latest', { exact: true })).toBeVisible();
  expect((await timeline(request)).find((b) => b.to === buildId)).toMatchObject({
    tagged: true,
    review: 'kept',
  });
  const history = page.getByRole('region', { name: 'History' });
  await expect(history.getByText('Rolled back').first()).toBeVisible();
  await expect(history.getByText('Rolled forward').first()).toBeVisible();
  expect(base).not.toBe('');
});

test('the first build has no notes: the review says so', async ({ page, request }) => {
  const tl = await timeline(request);
  const first = tl.at(-1)?.from ?? '';
  await signIn(page);
  await page.goto(`/maintainer/apis/${APIID}/builds/${first}/notes`);
  await expect(page.getByText('No release notes for this build')).toBeVisible({ timeout: 30_000 });
});
