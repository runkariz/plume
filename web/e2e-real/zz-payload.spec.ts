import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The payload of a webhook event as the real API sends it: a payload schema with its sample, an event whose ref
 * names a connector model, and a ref the server could not read. Needs a Shopify package whose events carry
 * payloadSchemaRef/sampleRef (carts/create: schema + sample, customers/create: model:address, app/scopes_update:
 * refs to files that do not exist): PLUME_E2E_PAYLOAD=true.
 */
const PAYLOAD = process.env.PLUME_E2E_PAYLOAD === 'true';
const event = (key: string) => `/apis/shopify/triggers/${encodeURIComponent(key)}`;

for (const theme of THEMES) {
  test.describe(`trigger payload (${theme})`, () => {
    test.skip(!PAYLOAD, 'set PLUME_E2E_PAYLOAD=true with the payload Shopify package loaded');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('a payload schema shows its fields (dotted) and a collapsed sample', async ({ page }) => {
      await page.goto(event('carts/create'));
      const fields = page.getByRole('region', { name: 'Payload fields' });
      await expect(fields).toContainText('line_items[].sku');
      await expect(fields.getByText('required')).toBeVisible();
      await expect(page.getByLabel('Sample payload')).toBeHidden();
      await page.getByText('Sample payload, as in the package').click();
      await expect(page.getByLabel('Sample payload')).toContainText('"sku": "A-1"');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w31-real-payload-fields', theme);
    });

    test('a ref to a model links to the model page', async ({ page }) => {
      await page.goto(event('customers/create'));
      const head = page.getByRole('region', { name: 'Payload' });
      await expect(head).toContainText('The payload is the model');
      await expect(page.getByRole('region', { name: 'Payload fields' })).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(head, 'w31-real-payload-model', theme);
      await head.getByRole('link', { name: 'Address' }).click();
      await expect(page).toHaveURL(/\/documents\/model%3Aaddress$/);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    });

    test('refs the server could not read are said so, as text', async ({ page }) => {
      await page.goto(event('app/scopes_update'));
      const head = page.getByRole('region', { name: 'Payload' });
      await expect(head).toContainText('could not read it');
      await expect(head).toContainText('nope.json');
      await settle(page);
      await shotOf(head, 'w31-real-payload-unread', theme);
    });
  });
}
