import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * Related concepts and creating a set against the real API, on the Shopify and WooCommerce mini packages
 * (Product -> Image, Line Item and Variant, all documented by Shopify only). The file name sorts last.
 * What is checked: the page shows the server's evidence as it is, a Claude session is really started for the picked
 * concepts, a request with an accepted alias is accepted and echoed, and a maintainer on a server without a model
 * key is offered the Claude path only.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const APIS = ['shopify', 'woocommerce'];
const RELATED = `/models/related?apis=${APIS.join(',')}&concept=Product`;

const bar = (page: Page) => page.getByRole('region', { name: 'Create a model set' });

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`related concepts, real API (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('from a suggestion to its related concepts, with the evidence the server cites', async ({
      page,
    }) => {
      await page.goto(`/models/suggest?apis=${APIS.join(',')}`);
      await page.getByRole('link', { name: 'Related concepts of Product' }).click();
      await expect(page).toHaveURL(/\/models\/related\?apis=shopify,woocommerce&concept=Product/);
      await expect(bar(page)).toBeVisible();
      const list = page.getByRole('list', { name: 'Related concepts' });
      const names = await list.getByRole('heading', { level: 3 }).allTextContents();
      expect(names).toEqual(expect.arrayContaining(['Image', 'Line Item', 'Variant']));
      const variant = list
        .locator('li.related')
        .filter({ has: page.getByRole('heading', { name: 'Variant', exact: true }) });
      await expect(variant).toContainText('Shopify: id field');
      await expect(variant).toContainText('WooCommerce: not documented');
      await variant.getByText(/Evidence in the docs/).click();
      const quote = variant.locator('blockquote').first();
      await expect(quote).not.toBeEmpty();
      await expect(variant.getByText('products[].variants[].product_id')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w17-real-related', theme);
    });

    test('create with Claude starts a real set session for the picked concepts', async ({
      page,
      request,
    }) => {
      await page.goto(RELATED);
      await expect(bar(page)).toBeVisible();
      await expect(bar(page).getByRole('button', { name: 'Create with Claude' })).toBeDisabled();
      await page.getByRole('checkbox', { name: 'Variant', exact: true }).click();
      await page.getByRole('checkbox', { name: 'Image', exact: true }).click();
      await expect(bar(page)).toContainText('3 models: Product, Variant, Image');
      await bar(page).getByRole('button', { name: 'Create with Claude' }).click();
      const panel = page.getByRole('region', { name: 'Create the set with Claude' });
      await expect(panel).toBeVisible();
      const prompt = (await panel.getByLabel('Prompt for Claude').textContent()) ?? '';
      expect(prompt).toMatch(/get_set_context\("ss-[0-9a-f]+"\)/);
      expect(prompt).toContain('Product, Variant, Image');
      expect(prompt).toContain('submit_model_set(');
      // the server really holds the session, and says it is still open (snake_case: the client accepts it)
      const id = /get_set_context\("(ss-[0-9a-f]+)"\)/.exec(prompt)?.[1];
      const status = (await (
        await request.get(`${API}/v1/model-sets/sessions/${id}`)
      ).json()) as Record<string, unknown>;
      expect(status).toMatchObject({
        status: 'open',
        set_id: null,
        concepts: ['Product', 'Variant', 'Image'],
      });
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w17-real-set-with-claude', theme);
      // still waiting: the page does not move on by itself
      await page.waitForTimeout(3500);
      await expect(page).toHaveURL(/\/models\/related/);
    });
  });
}

test('an accepted alias reaches the server in the shape it takes, and comes back in the prompt', async ({
  request,
}) => {
  const res = await request.post(`${API}/v1/model-sets/sessions`, {
    data: {
      apis: APIS,
      concepts: ['Product', 'Variant'],
      aliases: [{ concept: 'Variant', names: { shopify: 'Variant', woocommerce: 'Variation' } }],
    },
  });
  expect(res.status()).toBe(200);
  const body = (await res.json()) as { claudePrompt: string; aliases: unknown[] };
  expect(body.aliases).toEqual([
    { concept: 'Variant', names: { shopify: 'Variant', woocommerce: 'Variation' } },
  ]);
  expect(body.claudePrompt).toMatch(/Treat .*Variation.* as Variant/);
});

test('a maintainer on a server without a model key is offered the Claude path only', async ({
  page,
  request,
}) => {
  // the server's own answer to "generate a set" without a key
  const refused = await request.post(`${API}/v1/model-sets/generate`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: { apis: APIS, concepts: ['Product', 'Variant'] },
  });
  expect(refused.status()).toBe(503);
  await signIn(page);
  await page.goto(RELATED);
  await expect(bar(page)).toBeVisible();
  await expect(bar(page).getByRole('button', { name: 'Generate the set' })).toHaveCount(0);
  await expect(bar(page)).toContainText('Server-side generation is not configured on this Plume');
  await page.getByRole('checkbox', { name: 'Variant', exact: true }).click();
  await bar(page).getByRole('button', { name: 'Create with Claude' }).click();
  await expect(page.getByRole('region', { name: 'Create the set with Claude' })).toBeVisible();
});
