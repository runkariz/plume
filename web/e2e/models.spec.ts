import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

for (const theme of THEMES) {
  test.describe(`canonical models (${theme})`, () => {
    test.use({ theme });

    test('pick apps → suggested models → mapping view', async ({ page }) => {
      // 1 pick
      await page.goto('/models');
      await expect(page.getByRole('checkbox', { name: /Shopify Admin REST/ })).toBeVisible();
      for (const name of [/Shopify Admin REST/, /WooCommerce REST/, /Mirakl Seller API/])
        await page.getByRole('checkbox', { name }).check({ force: true });
      await expect(page.getByText('3 selected')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-09-pick-apps', theme);

      // 2 suggestions
      await page.getByRole('button', { name: 'Suggest models →' }).click();
      await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-10-suggested-models', theme);

      // 3 generate → mapping view with the stored snapshot's nodes and edges
      await page.getByRole('button', { name: 'Generate Inventory' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible();
      await expect(page.locator('.react-flow__node')).toHaveCount(7 + 14 + 3); // canonical + api fields + groups
      await expect(page.locator('.react-flow__edge')).toHaveCount(14);
      await expect(page.locator('.react-flow__edge.selected')).toHaveCount(1);
      await expect(
        page.getByRole('heading', { name: 'quantity_available ← Shopify' }),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w4-11-model-mapping-view', theme);

      // clicking an edge selects that mapping
      await page
        .locator('.react-flow__edge[aria-label="manage_stock from Shopify (derived)"]')
        .click({ force: true });
      await expect(page.getByRole('heading', { name: 'manage_stock ← Shopify' })).toBeVisible();
      await expect(page.getByText('derived: transform')).toBeVisible();
      await expect(page.getByText('not null = true', { exact: true }).last()).toBeVisible();
    });
  });
}

for (const theme of THEMES) {
  test.describe(`generation session (${theme})`, () => {
    test.use({ theme });

    test('Order has no snapshot: the session waits for a draft; a refused draft lists its issues; an accepted one opens the model', async ({
      page,
    }) => {
      // the maintainer key lives in memory only: sign in, then move around inside the app
      await page.goto('/maintainer');
      await page.getByLabel('Access token').fill('pl_e2e_token_value');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
      await page.getByRole('link', { name: 'Models', exact: true }).click();
      for (const name of [/Shopify Admin REST/, /WooCommerce REST/, /Mirakl Seller API/])
        await page.getByRole('checkbox', { name }).check({ force: true });
      await page.getByRole('button', { name: 'Suggest models →' }).click();
      await page.getByRole('button', { name: 'Generate Order' }).click();

      const panel = page.getByRole('region', { name: 'Generation session' });
      await expect(
        panel.getByRole('heading', { name: 'Waiting for a draft: Order' }),
      ).toBeVisible();
      await expect(panel.getByLabel('Prompt for Claude')).toContainText('get_model_context(');
      await expect(panel.getByLabel('Command to add the maintainer connector')).toContainText(
        '/maintainer/mcp',
      );
      await panel.getByRole('button', { name: 'See what Plume gives Claude' }).click();
      const pack = panel.getByRole('region', { name: 'Evidence pack' });
      await expect(pack.getByRole('region', { name: 'Evidence for Shopify' })).toContainText(
        '3 fields',
      );
      await pack.getByRole('button', { name: /^Show Shopify fields/ }).click();
      await expect(pack.getByText('3 of 5 fields shown').first()).toBeVisible();
      await pack.getByRole('button', { name: 'Load more fields' }).first().click();
      await expect(pack.getByText('5 of 5 fields shown').first()).toBeVisible();

      // a refused draft shows the server's issue codes and stores nothing
      await panel
        .getByLabel('Draft JSON')
        .fill('{"name":"Order","fields":[{"name":"total"}],"refuse":"quote"}');
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(panel.getByRole('alert').getByText('QUOTE_NOT_FOUND')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w7-generate-session', theme);

      await panel.getByLabel('Draft JSON').fill('{"name":"Order","fields":[{"name":"sku"}]}');
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible();
      await expect(page.getByText('Generated, unverified')).toBeVisible();
    });
  });
}

test('picking a mapping from the list zooms the graph to it, and the wheel scrolls the page', async ({
  page,
}) => {
  await page.goto('/models/snap_8f3a21');
  await expect(page.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible();
  const scale = () =>
    page
      .locator('.react-flow__viewport')
      .evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a);
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
  const overview = await scale();

  await page
    .getByRole('combobox', { name: 'Mapping' })
    .selectOption({ label: 'lead_time_days ← Mirakl' });
  await expect(page.getByRole('heading', { name: 'lead_time_days ← Mirakl' })).toBeVisible();
  await expect
    .poll(scale, { message: 'the view zooms to the picked field' })
    .toBeGreaterThan(overview * 1.05);

  // clicking in the graph selects without moving the view
  const zoomed = await scale();
  await page
    .locator('.react-flow__edge[aria-label="manage_stock from Shopify (derived)"]')
    .click({ force: true });
  await expect(page.getByRole('heading', { name: 'manage_stock ← Shopify' })).toBeVisible();
  expect(Math.abs((await scale()) - zoomed)).toBeLessThan(0.001);

  // the page scrolls over the canvas (zoom is Ctrl/Cmd + wheel, the controls or pinch)
  const box = await page.locator('.flow').boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move((box?.x ?? 0) + 200, (box?.y ?? 0) + 200);
  const before = await page.evaluate(() => window.scrollY);
  await page.mouse.wheel(0, 400);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(before);
  expect(await scale()).toBeCloseTo(zoomed, 3);
});

test('suggestions need two APIs', async ({ page }) => {
  await page.goto('/models/suggest?apis=shopify');
  await expect(page.getByText('Pick at least two APIs')).toBeVisible();
});

test('a missing model shows not found', async ({ page }) => {
  await page.goto('/models/snap_nope');
  await expect(page.getByRole('alert')).toContainText('Model not found');
});
