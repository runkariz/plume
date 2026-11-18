import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Every server of an environment, and the auth URLs resolved per environment, on real packages: bol Retailer (api +
 * auth), TikTok Shop (api, auth, auth_2; US and Rest of World) and Metro Markets (api .. api_6).
 * Needs those three packages loaded (one `load` each): PLUME_E2E_SERVERS=true.
 */
const SERVERS = process.env.PLUME_E2E_SERVERS === 'true';

for (const theme of THEMES) {
  test.describe(`environment servers (${theme})`, () => {
    test.skip(
      !SERVERS,
      'set PLUME_E2E_SERVERS=true with bol-retailer, tiktokshop and metromarkets loaded',
    );
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('bol Retailer shows its API and its Auth server', async ({ page }) => {
      await page.goto('/apis/bol-retailer');
      const card = page.getByRole('region', { name: 'Environments' });
      const prod = card.getByRole('group', { name: 'Servers of production' });
      await expect(prod.locator('.env-server').first()).toContainText('API');
      await expect(prod).toContainText('https://api.bol.com');
      await expect(prod).toContainText('Auth');
      await expect(prod).toContainText('https://login.bol.com');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w35-real-bol-servers', theme);
    });

    test('TikTok Shop shows Auth and Auth 2 in both environments', async ({ page }) => {
      await page.goto('/apis/tiktokshop');
      const card = page.getByRole('region', { name: 'Environments' });
      await expect(card.getByRole('group')).toHaveCount(2);
      const us = card.getByRole('group', { name: 'Servers of US' });
      await expect(us).toContainText('https://services.us.tiktokshop.com');
      await expect(us).toContainText('Auth 2');
      await expect(us).toContainText('https://auth.tiktok-shops.com');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(card, 'w35-real-tiktok-servers', theme);
    });

    test('Metro Markets shows API to API 6', async ({ page }) => {
      await page.goto('/apis/metromarkets');
      const card = page.getByRole('region', { name: 'Environments' });
      const sandbox = card.getByRole('group', { name: 'Servers of sandbox' });
      await expect(sandbox.locator('.env-server')).toHaveCount(6);
      await expect(sandbox).toContainText('API 6');
      await expect(sandbox).toContainText(
        'https://service-multimarket-central.sandbox.infra.metro-markets.cloud',
      );
      await shotOf(card, 'w35-real-metro-servers', theme);
    });

    test('bol auth page: the token and authorize URLs resolved for production', async ({
      page,
    }) => {
      await page.goto('/apis/bol-retailer/auth/oauth2-authorization-code');
      const how = page.getByRole('region', { name: 'How it works' });
      await expect(how).toContainText('{{app_env.servers.auth}}/token');
      const token = how.getByRole('list', {
        name: 'Token URL per environment',
      });
      await expect(token).toContainText('production: https://login.bol.com/token');
      await expect(
        how.getByRole('list', {
          name: 'Authorize URL per environment',
        }),
      ).toContainText('production: https://login.bol.com/authorize');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(how, 'w35-real-bol-auth-urls', theme);
    });

    test('TikTok auth page: each URL resolved for US and Rest of World', async ({ page }) => {
      await page.goto('/apis/tiktokshop/auth/oauth2-authorization-code');
      const how = page.getByRole('region', { name: 'How it works' });
      const authorize = how.getByRole('list', {
        name: 'Authorize URL per environment',
      });
      await expect(authorize).toContainText(
        'US: https://services.us.tiktokshop.com/open/authorize',
      );
      await expect(authorize).toContainText(
        'Rest of World (ROW): https://services.tiktokshop.com/open/authorize',
      );
      await expect(
        how.getByRole('list', {
          name: 'Token URL per environment',
        }),
      ).toContainText('US: https://auth.tiktok-shops.com/api/v2/token/get');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(how, 'w35-real-tiktok-auth-urls', theme);
    });
  });
}
