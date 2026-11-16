import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES, pickMapping, openModel } from './helpers';

/** A real 40-field Order model (Shopify + WooCommerce + Mirakl), copied from a live snapshot into the mocks. */
const MODEL = '/models/m-38f24111baf1076f44c9cfa7';

const viewportScale = (page: Page) =>
  page
    .locator('.react-flow__viewport')
    .evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a);
const viewportY = (page: Page) =>
  page
    .locator('.react-flow__viewport')
    .evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).f);

for (const width of [1440, 375]) {
  for (const theme of THEMES) {
    test.describe(`big model at ${width} px (${theme})`, () => {
      test.use({ theme, viewport: { width, height: width === 375 ? 800 : 900 } });

      test('opens as a readable table with display names, filters, citation links', async ({
        page,
      }) => {
        await openModel(page, MODEL);
        await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible();
        await expect(page.getByRole('radio', { name: 'Table' })).toBeChecked();
        const table = page.getByRole('table', { name: /How each API fills each field/ });
        await expect(table.getByRole('row')).toHaveCount(41);
        if (width > 640) {
          await expect(table.getByRole('columnheader')).toHaveText([
            'Field',
            'Shopify',
            'WooCommerce',
            'Mirakl',
          ]);
          // readable: table text is at least 13 px
          const px = await table
            .locator('td')
            .first()
            .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
          expect(px).toBeGreaterThanOrEqual(13);
        }
        await expect(page.getByText('26 of 40')).toBeVisible(); // the Coverage card is not clipped
        await settle(page);
        await expectNoSeriousA11y(page);
        await shot(page, `w9-model-table-${width}`, theme);

        // nothing scrolls sideways
        const wide = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        );
        expect(wide, 'the page scrolls sideways').toBe(false);

        await page.getByRole('searchbox', { name: 'Filter fields' }).fill('display_number');
        await expect(page.getByText('1 of 40 fields')).toBeVisible();
        const row = page.getByRole('rowheader', { name: /^display_number/ }).locator('xpath=..');
        await row.locator('summary').first().click();
        await row.getByRole('link').first().click();
        await expect(page).toHaveURL(/\/apis\/shopify\/documents\//);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        await settle(page);
        await expectNoSeriousA11y(page);
        await shot(page, `w9-document-${width}`, theme);
      });

      test('graph view: focused on one field first, the whole model on request at a readable zoom', async ({
        page,
      }) => {
        await openModel(page, MODEL);
        await page.getByRole('radio', { name: 'Graph' }).click({ force: true });
        await expect(page.getByRole('radio', { name: 'Selected field' })).toBeChecked();
        await expect(page.locator('.react-flow__node-canonical')).toHaveCount(1);
        await settle(page);
        await expectNoSeriousA11y(page);
        await shot(page, `w9-model-graph-focus-${width}`, theme);

        await pickMapping(page, /^display_number ← WooCommerce/);
        await expect(page.locator('.react-flow__node-canonical')).toContainText('display_number');

        await page.getByRole('radio', { name: 'Whole model' }).click({ force: true });
        await expect(page.locator('.react-flow__node-canonical')).toHaveCount(40);
        // a readable zoom: node text is about 12 px or more (no "fit everything")
        await expect.poll(() => viewportScale(page)).toBeGreaterThanOrEqual(0.85);
        const scale = await viewportScale(page);
        const pathPx = await page
          .locator('.g-path')
          .first()
          .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
        expect(pathPx * scale).toBeGreaterThanOrEqual(11.5);
        await settle(page);
        await expectNoSeriousA11y(page);
        await shot(page, `w9-model-graph-all-${width}`, theme);

        if (width > 640) {
          // the wheel pans the graph vertically inside its window; the page stays put
          const box = await page.locator('.flow').boundingBox();
          // over the canvas, to the right of the control box that covers its left side
          await page.mouse.move((box?.x ?? 0) + (box?.width ?? 800) - 150, (box?.y ?? 0) + 300);
          const y0 = await viewportY(page);
          const pageY0 = await page.evaluate(() => window.scrollY);
          await page.mouse.wheel(0, 500);
          await expect.poll(() => viewportY(page)).toBeLessThan(y0);
          expect(await page.evaluate(() => window.scrollY)).toBe(pageY0);
        }
      });
    });
  }
}

test('the Table / Graph choice is a labelled control and a small model still opens as a graph', async ({
  page,
}) => {
  await page.goto('/models/snap_8f3a21');
  await expect(page.getByRole('radio', { name: 'Graph' })).toBeChecked();
  await expect(page.locator('.react-flow__node-canonical')).toHaveCount(7);
  await page.getByRole('radio', { name: 'Table' }).click({ force: true });
  await expect(page.getByRole('table')).toBeVisible();
});
