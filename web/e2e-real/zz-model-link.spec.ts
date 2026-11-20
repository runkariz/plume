import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Fields whose type refers to a model of the package (`modelId`): the type links to the model. Real TikTok Shop model
 * documents (a field `detail` of type activateproducterrordetail, and an array of activateproductextraerror).
 * Needs the real TikTok Shop package loaded as `tiktokshop`: PLUME_E2E_MODELID=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_MODELID === 'true';
const DOC = 'model:activateproducterror';

for (const theme of THEMES) {
  test.describe(`field model links, real data (${theme})`, () => {
    test.skip(!ON, 'needs the real TikTok Shop package: PLUME_E2E_MODELID=true');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a field typed by a model links to it; an array of a model shows the type and the model', async ({
      page,
      request,
    }) => {
      const body = (await (
        await request.get(`${API}/v1/apis/tiktokshop/documents/${encodeURIComponent(DOC)}`)
      ).json()) as { fields: { name: string; type: string | null; modelId?: string | null }[] };
      expect(body.fields.find((f) => f.name === 'detail')?.modelId).toBe(
        'model:activateproducterrordetail',
      );
      await page.goto(`/apis/tiktokshop/documents/${encodeURIComponent(DOC)}`);
      const fields = page.getByRole('region', { name: /fields/i }).first();
      const link = fields.getByRole('link', { name: 'activateproducterrordetail', exact: true });
      await expect(link).toHaveAttribute('title', 'model:activateproducterrordetail');
      const extra = fields.getByRole('row').filter({ hasText: 'detail.extra_errors' }).first();
      await expect(extra).toContainText('array → activateproductextraerror');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(fields, 'w44-real-field-model-links', theme);
      await link.click();
      await expect(page).toHaveURL(/\/documents\/model%3Aactivateproducterrordetail$/);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    });
  });
}
