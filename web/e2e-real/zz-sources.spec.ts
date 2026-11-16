import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The real API: GET /v1/apis/{api} carries `sources` and `extractedAt` (packages loaded after the package metadata
 * was recorded); the public page shows them linked, and an old build without them shows nothing. Today's packages have
 * no manifest sources[], so the server falls back to the manifest's one source url as a docs source.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';

const IDS = ['shopify', 'woocommerce', 'mirakl'];

for (const theme of THEMES) {
  test.describe(`sources, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    for (const id of IDS)
      test(`the API page of ${id} shows what the server says: http(s) sources only, and when it was extracted`, async ({
        page,
        request,
      }) => {
        const detail = (await (await request.get(`${API}/v1/apis/${id}`)).json()) as {
          sources: { url: string; kind: string }[] | null;
          extractedAt: string | null;
        };
        await page.goto(`/apis/${id}`);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const line = page.getByTestId('sources-line');
        const shown = (detail.sources ?? []).length > 0 || Boolean(detail.extractedAt);
        if (!shown) {
          await expect(line).toHaveCount(0);
          return;
        }
        await expect(line).toBeVisible();
        for (const s of detail.sources ?? [])
          await expect(
            page
              .getByTestId('sources')
              .locator(`a[href="${new URL(s.url).toString()}"]`)
              .first(),
          ).toBeAttached();
        if (detail.extractedAt) await expect(line).toContainText('Extracted');
        await settle(page);
        await expectNoSeriousA11y(page);
        await shotOf(page.locator('.titlerow'), 'w24-real-api-sources', theme);
      });
  });
}

// needs two builds with release notes: the frozen Shopify packages, as zz-release.spec.ts (PLUME_E2E_RELEASE_NOTES=true)
test.describe('maintainer review', () => {
  test.skip(
    process.env.PLUME_E2E_RELEASE_NOTES !== 'true',
    'needs the frozen Shopify packages loaded: PLUME_E2E_RELEASE_NOTES=true',
  );
  test('the maintainer review shows the real run id, the manifest fallback source, and that no conflict check was recorded', async ({
    page,
    request,
  }) => {
    const token = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
    const auth = { Authorization: `Bearer ${token}` };
    const tl = (await (
      await request.get(`${API}/v1/apis/shopify/release-notes`, { headers: auth })
    ).json()) as {
      items: { to: string }[];
    };
    const build = tl.items[0]?.to ?? '';
    const notes = (await (
      await request.get(`${API}/v1/apis/shopify/builds/${build}/release-notes`, { headers: auth })
    ).json()) as {
      package: { to: { runId?: string; sources?: { url: string; fallback?: boolean }[] } };
      conflictCheck?: { checked: number; notCompared: number };
    };
    await page.goto('/maintainer');
    await page.getByLabel('Access token').fill(token);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
    await page.goto(`/maintainer/apis/shopify/builds/${build}/notes`);
    const panel = page.getByRole('region', { name: 'Sources and conflicts' });
    await expect(panel).toBeVisible({ timeout: 30_000 });
    if (notes.package.to.runId) await expect(panel).toContainText(notes.package.to.runId);
    for (const s of notes.package.to.sources ?? [])
      await expect(panel.locator(`a[href="${new URL(s.url).toString()}"]`)).toBeVisible();
    if (notes.package.to.sources?.some((s) => s.fallback))
      await expect(panel).toContainText("only the manifest's source url");
    if (notes.conflictCheck?.checked === 0 && notes.conflictCheck.notCompared === 0) {
      await expect(panel.getByTestId('conflict-check')).toContainText(
        'no conflict check was recorded',
      );
      await expect(panel).not.toContainText('found no conflicts');
    }
    await expectNoSeriousA11y(page);
    await shotOf(panel, 'w24-real-review-sources', 'light');
  });
});
