import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/** The answer-quality card as the real API sends it: the top-1 score under its new name, and the small-set note. */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';

for (const theme of THEMES) {
  test.describe(`answer quality, real data (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('Top-1 hit rate with its hint; a small gold set carries the server note', async ({
      page,
      request,
    }) => {
      const q = (
        (await (await request.get(`${API}/v1/apis/test-catalog-api`)).json()) as {
          quality: {
            top1Rate?: number;
            citationHitRate?: number;
            goldQuestions: number;
            note?: string | null;
          };
        }
      ).quality;
      expect(q.citationHitRate).toBeUndefined(); // the old key is gone from the API
      expect(q.top1Rate).toBeDefined();
      expect(q.goldQuestions).toBeLessThan(10);
      expect(q.note).toContain('sanity check');
      await page.goto('/apis/test-catalog-api');
      const card = page.getByRole('heading', { name: 'Answer quality' }).locator('..');
      await expect(card).toContainText('Top-1 hit rate');
      await expect(card).toContainText('Share of questions whose answer ranks first.');
      await expect(card).not.toContainText('Citation hit');
      await expect(card.getByRole('list', { name: 'About this score' })).toContainText(
        q.note as string,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w34-real-quality-note', theme);
    });
  });
}
