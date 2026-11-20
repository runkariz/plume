import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * An auth question brings in the API's own app document with no snippet and no ranks (TikTok Shop, "how to sign
 * requests"): the search page shows it cleanly. Needs the real TikTok Shop package loaded as `tiktokshop`:
 * PLUME_E2E_TIKTOK=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_TIKTOK === 'true';
const QUESTION = 'how to sign requests';

for (const theme of THEMES) {
  test.describe(`search, added hit, real data (${theme})`, () => {
    test.skip(!ON, 'needs the real TikTok Shop package: PLUME_E2E_TIKTOK=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the app hit has no snippet and no ranks; the page shows no empty box and no "null"', async ({
      page,
      request,
    }) => {
      const res = await request.post(`${API}/v1/apis/tiktokshop/search`, {
        data: { query: QUESTION, mode: 'hybrid', kind: 'all', topK: 5 },
      });
      const body = (await res.json()) as {
        results: {
          kind: string;
          snippet: string;
          denseRank: number | null;
          textRank: number | null;
        }[];
      };
      const added = body.results.find((r) => r.kind === 'app');
      expect(added, 'the API sends its app document').toBeDefined();
      expect(added?.snippet).toBe('');
      expect(added?.denseRank).toBeNull();
      expect(added?.textRank).toBeNull();
      await page.goto('/apis/tiktokshop/try');
      await page.getByLabel('Question or search text').fill(QUESTION);
      await page.getByRole('button', { name: 'Run' }).click();
      const hit = page.locator('.res').filter({ hasText: 'Added to the results' });
      await expect(hit).toHaveCount(1);
      await expect(hit).not.toContainText(/null|undefined|NaN/);
      await expect(hit.locator('p.muted')).toHaveCount(0);
      await expect(hit).toContainText('dense –');
      // a long path wraps inside its card (no sideways scroll of the page)
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('list').filter({ has: hit }).first(),
        'w43-real-search-added-hit',
        theme,
      );
    });
  });
}
