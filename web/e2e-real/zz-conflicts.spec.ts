import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The docs state different values for a limit (x-kariz-conflicts): every statement with its place, examples marked, none
 * picked. No package carries it yet: needs a shopify-mini copy whose products request.json has an `x-kariz-conflicts`
 * of "the page size" (description 128, param:limit 250, an example on a page), loaded as shopify:
 * PLUME_E2E_CONFLICTS=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_CONFLICTS === 'true';
const DOC = 'endpoint:GET~/admin/api/{version}/products.json';

for (const theme of THEMES) {
  test.describe(`conflicting statements, real data (${theme})`, () => {
    test.skip(!ON, 'set PLUME_E2E_CONFLICTS=true with the edited shopify-mini loaded');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('every statement with its place; the example marked; the page linked', async ({
      page,
      request,
    }) => {
      const body = (await (
        await request.get(`${API}/v1/apis/shopify/documents/${encodeURIComponent(DOC)}`)
      ).json()) as { conflicts: { limit: string; statements: { where: string }[] }[] };
      expect(body.conflicts).toHaveLength(1);
      expect(body.conflicts[0]?.statements).toHaveLength(3);
      await page.goto(`/apis/shopify/documents/${encodeURIComponent(DOC)}`);
      const card = page.getByRole('region', { name: 'Conflicting statements' });
      await expect(card).toContainText('The docs state different values for the page size:');
      const items = card
        .getByRole('list', { name: 'Statements about the page size' })
        .getByRole('listitem');
      await expect(items).toHaveCount(3);
      await expect(items.nth(0)).toContainText(
        'Results are limited to 128 per page. in the description',
      );
      await expect(items.nth(1)).toContainText('The maximum value is 250. in parameter limit');
      await expect(items.nth(2).getByText('example')).toBeVisible();
      await expect(items.nth(2).getByRole('link')).toHaveAttribute(
        'href',
        'https://shopify.dev/docs/api/usage/pagination-rest',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w47-real-conflicts', theme);
    });
  });
}
