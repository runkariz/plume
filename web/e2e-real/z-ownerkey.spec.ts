import { expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * The owner key against the real API: an anonymous model is stored over HTTP (the server answers with its `ownerKey`
 * once, as the MCP view now shows it), and pasting that key on the Models page lists the model; a mistyped key is
 * refused. The file name sorts late: the model it stores must not change what the other specs see.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const APIS = ['test-catalog-api', 'second-catalog-api'];
const DRAFTS = resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/drafts');
const good = JSON.parse(readFileSync(resolve(DRAFTS, 'catalog-order-good.json'), 'utf8')) as object;
const RUN = Date.now().toString(36);

for (const theme of THEMES) {
  test.describe(`owner key, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a key the server handed out once lists its model when pasted', async ({
      page,
      request,
    }) => {
      const session = (await (
        await request.post(`${API}/v1/models/generate`, {
          data: { apis: APIS, concept: 'Order', engine: 'claude', force: true },
        })
      ).json()) as { sessionId: string };
      const res = await request.post(`${API}/v1/models/sessions/${session.sessionId}/draft`, {
        data: { ...good, name: `Order key ${RUN}-${theme}` },
      });
      expect(res.status(), await res.text()).toBe(201);
      const stored = (await res.json()) as {
        model: { id: string; name: string };
        ownerKey?: string;
      };
      expect(stored.ownerKey, 'a new lineage without a token gets an owner key').toBeTruthy();
      const key = stored.ownerKey ?? '';

      await page.goto('/models');
      const region = page.getByRole('region', { name: 'Add an owner key' });
      await region.getByText(/Have an owner key/).click();
      await region.getByLabel('Owner key').fill(`${key}x`); // mistyped
      await region.getByRole('button', { name: 'Add key' }).click();
      await expect(region.getByRole('alert')).toContainText(
        'No model or model set belongs to this key',
      );
      await region.getByLabel('Owner key').fill(key);
      await region.getByRole('button', { name: 'Add key' }).click();
      await expect(region.getByRole('status')).toContainText('Added: 1 model');
      const yours = page.getByRole('region', { name: 'Your models' });
      await expect(
        yours.getByRole('link', { name: new RegExp(`Order key ${RUN}-${theme}`) }),
      ).toBeVisible();
      expect(page.url()).not.toContain(key);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w18-real-owner-key', theme);
    });
  });
}
