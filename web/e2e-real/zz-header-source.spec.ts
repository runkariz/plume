import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Where an OAuth2/API-key header comes from (headerPrefix, headerSource, headerEvidence, headerNote), as the real API
 * sends it. No live package carries the fields yet: needs copies of shopify-mini (auth unit with headerName
 * Authorization, headerPrefix "Bearer", headerSource "standard:rfc6750") and mirakl-mini (api-key-authorization with
 * headerPrefix "Bearer ", headerSource "vendor" and a headerEvidence), loaded as shopify and mirakl:
 * PLUME_E2E_HEADER=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_HEADER === 'true';
const NOTE = "OAuth 2.0 standard (RFC 6750), not stated in the vendor's docs";

for (const theme of THEMES) {
  test.describe(`header source, real data (${theme})`, () => {
    test.skip(!ON, 'set PLUME_E2E_HEADER=true with the edited shopify-mini and mirakl-mini loaded');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the standard header: the label in the open, no quote, one space', async ({
      page,
      request,
    }) => {
      const scheme = (await (
        await request.get(`${API}/v1/apis/shopify/auth/oauth2-authorization-code`)
      ).json()) as {
        headerSource: string;
        headerEvidence: string | null;
        headerNote: string;
        headerFormat?: string | null;
      };
      expect(scheme.headerSource).toBe('standard:rfc6750');
      expect(scheme.headerEvidence).toBeNull();
      expect(scheme.headerNote).toBe(NOTE);
      // newer servers send the string to show (one space, whatever the prefix ends in)
      if (scheme.headerFormat !== undefined)
        expect(scheme.headerFormat).toBe('Authorization: Bearer <token>');
      await page.goto('/apis/shopify?section=auth');
      const list = page.getByRole('region', { name: 'Authentication' });
      await expect(list.getByText('Authorization: Bearer <token>')).toBeVisible();
      await expect(list.getByText(NOTE)).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(list, 'w45-real-header-standard-list', theme);
      await page.goto('/apis/shopify/auth/oauth2-authorization-code');
      const how = page.getByRole('region', { name: 'How it works' });
      await expect(how.getByText('Authorization: Bearer <token>')).toBeVisible();
      await expect(how.getByText(NOTE)).toBeVisible();
      await expect(how.locator('blockquote')).toHaveCount(0);
      await expectNoSeriousA11y(page);
      await shotOf(how, 'w45-real-header-standard', theme);
    });

    test('the vendor header: its quote; a prefix with a trailing space still shows one space', async ({
      page,
    }) => {
      await page.goto('/apis/mirakl/auth/api-key-authorization');
      const how = page.getByRole('region', { name: 'How it works' });
      await expect(how.getByText('Authorization: Bearer <token>')).toBeVisible();
      await expect(how.locator('blockquote')).toContainText(
        'Pass your API key in the Authorization header of every request.',
      );
      await expect(how.getByText(NOTE)).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(how, 'w45-real-header-vendor', theme);
    });
  });
}
