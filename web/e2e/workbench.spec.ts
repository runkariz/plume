import { expect, type Locator } from '@playwright/test';
import { expectNoSeriousA11y, pickMapping, settle, shot, test, THEMES, openModel } from './helpers';

async function boxOf(locator: Locator) {
  const b = await locator.boundingBox();
  if (!b) throw new Error('not visible');
  return b;
}

/** The model graph with its control box and the mapping detail beside it, and the brand mark. */
const ORDER = '/models/m-38f24111baf1076f44c9cfa7'; // the 40-field Order model of the mock (a live snapshot)
const SMALL = '/models/snap_8f3a21';
const NESTED = '/models/u-nested0000000000000000000000001'; // a model with nested objects and arrays

for (const theme of THEMES) {
  test.describe(`model workbench (${theme})`, () => {
    // a desktop screen: the control box is open by default from 1400 px
    test.use({ theme, viewport: { width: 1440, height: 900 } });

    test('the detail is next to the graph without scrolling, and the control box is on the canvas', async ({
      page,
    }) => {
      await page.goto(SMALL);
      const canvas = page.getByRole('group', { name: /Mapping graph/ });
      const detail = page.getByRole('region', { name: 'Mapping detail' });
      await expect(detail).toBeVisible();
      const [c, d, controls] = await Promise.all([
        canvas.boundingBox(),
        detail.boundingBox(),
        page.getByRole('complementary', { name: 'Graph controls' }).boundingBox(),
      ]);
      // side by side on a wide screen, the detail inside the first screen, the box inside the canvas
      expect((d?.x ?? 0) >= (c?.x ?? 0) + (c?.width ?? 0) - 1).toBe(true);
      expect((d?.y ?? 9999) + 100).toBeLessThan(page.viewportSize()?.height ?? 800);
      expect((controls?.x ?? 0) >= (c?.x ?? 0)).toBe(true);
      expect((controls?.x ?? 0) + (controls?.width ?? 0) <= (c?.x ?? 0) + (c?.width ?? 0)).toBe(
        true,
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-graph-small', theme);
    });

    test('whole model, WooCommerce only: the others are greyed out, nothing is hidden, the URL keeps it', async ({
      page,
    }) => {
      await openModel(page, ORDER);
      await expect(page.getByRole('heading', { level: 1, name: 'Order' })).toBeVisible();
      await page.getByRole('radio', { name: 'Graph' }).click({ force: true });
      await expect(page.getByRole('radio', { name: 'Graph' })).toBeChecked();
      await page.getByRole('radio', { name: 'Whole model' }).click({ force: true });
      await expect(page.getByRole('radio', { name: 'Whole model' })).toBeChecked();
      await expect(page.locator('.react-flow__node-canonical')).toHaveCount(40);
      const nodes = await page.locator('.react-flow__node').count();
      const box = page.getByRole('complementary', { name: 'Graph controls' });
      await box.getByRole('checkbox', { name: 'Shopify' }).click();
      await box.getByRole('checkbox', { name: 'Mirakl' }).click();
      await expect(page).toHaveURL(/show=woocommerce/);
      await expect(page.locator('.react-flow__node.dim').first()).toBeVisible();
      expect(await page.locator('.react-flow__node').count()).toBe(nodes); // greyed out, not hidden
      await expect(page.locator('.react-flow__edge.dim').first()).toBeAttached();
      await expect(page.locator('.react-flow__edge:not(.dim)').first()).toBeAttached();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-graph-woo-only', theme);
      // a link keeps the filter
      await page.reload();
      await expect(page.getByRole('checkbox', { name: 'Shopify' })).not.toBeChecked();
      await expect(page.getByRole('checkbox', { name: 'WooCommerce' })).toBeChecked();
    });

    test('selected field: the view fits the selection and the detail panel shows the mapping', async ({
      page,
    }) => {
      await openModel(page, ORDER);
      await page.getByRole('radio', { name: 'Graph' }).click({ force: true });
      await expect(page.getByRole('radio', { name: 'Graph' })).toBeChecked();
      await expect(page.getByRole('radio', { name: 'Selected field' })).toBeChecked();
      await pickMapping(page, /^display_number ← WooCommerce/);
      const detail = page.getByRole('region', { name: 'Mapping detail' });
      await expect(
        detail.getByRole('heading', { name: 'display_number ← WooCommerce' }),
      ).toBeVisible();
      await expect(page).toHaveURL(/field=display_number/);
      // nothing of the single field is hidden under the box or outside the canvas
      const canvas = await boxOf(page.getByRole('group', { name: /Mapping graph/ }));
      const controls = await boxOf(page.getByRole('complementary', { name: 'Graph controls' }));
      // the fit is applied a moment after the field changes: wait for it, then nothing of the field may sit under
      // the box or outside the canvas
      await expect
        .poll(async () => {
          for (const n of await page
            .locator('.react-flow__node-canonical, .react-flow__node-apiField')
            .all()) {
            const b = await boxOf(n);
            if (b.x < controls.x + controls.width - 2) return 'under the control box';
            if (b.x + b.width > canvas.x + canvas.width + 2) return 'outside the canvas';
          }
          return 'fits';
        })
        .toBe('fits');
      // the canvas is as tall as the single field needs, not the whole-model window
      expect(canvas.height).toBeLessThan(600);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-graph-selected-field', theme);
    });

    test('nested fields: expandable rows in the table, paths in the graph and its list', async ({
      page,
    }) => {
      await page.goto(`${NESTED}?view=table`);
      await expect(page.getByRole('heading', { level: 1, name: 'Order with lines' })).toBeVisible();
      const names = () =>
        page.locator('table.mtable-grid th[scope="row"] .mtable-name').evaluateAll((els) =>
          els.map((el) =>
            [...el.childNodes]
              .filter((n) => n.nodeType === Node.TEXT_NODE)
              .map((n) => n.textContent)
              .join('')
              .trim(),
          ),
        );
      expect(await names()).toEqual([
        'id',
        'customer',
        'name',
        'email',
        'lines',
        'sku',
        'price',
        'amount',
        'currency',
      ]);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w15-nested-table', theme);
      await page.getByRole('button', { name: 'Collapse lines', exact: true }).click();
      expect(await names()).toEqual(['id', 'customer', 'name', 'email', 'lines']);
      await page.getByRole('button', { name: 'Expand lines', exact: true }).click();
      // the graph: the mapped fields by canonical path, the list indented, the detail by path
      await page.goto(`${NESTED}?view=graph&scope=all`);
      await expect(page.locator('.react-flow__node-canonical')).toHaveCount(7);
      await page.getByRole('option', { name: /lines\[\]\.price\.amount ← Shopify/ }).click();
      await expect(
        page
          .getByRole('region', { name: 'Mapping detail' })
          .getByRole('heading', { name: 'lines[].price.amount ← Shopify' }),
      ).toBeVisible();
      await expect(page).toHaveURL(/field=lines/);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w15-nested-graph', theme);
    });

    test('keyboard: the mapping list is one tab stop, arrows move, Enter selects', async ({
      page,
    }) => {
      await page.goto(SMALL);
      const list = page.getByRole('listbox', { name: 'Mappings' });
      await list.focus();
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Enter');
      const selected = list.getByRole('option', { selected: true });
      await expect(selected).toHaveCount(1);
      const name = (await selected.locator('.wb-row-name').textContent()) ?? '';
      await expect(
        page.getByRole('region', { name: 'Mapping detail' }).getByRole('heading'),
      ).toContainText(name);
      // the box collapses from the keyboard too
      const toggle = page.getByRole('button', { name: /Filter and mappings/ });
      await toggle.focus();
      await page.keyboard.press('Enter');
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await expect(list).toBeHidden();
    });

    test('the header shows the brand mark of this theme', async ({ page }) => {
      await page.goto('/');
      const link = page.getByRole('link', { name: 'Plume home' });
      const shown = theme === 'dark' ? 'plume-mark-white-96.png' : 'plume-mark-dark-96.png';
      const hidden = theme === 'dark' ? 'plume-mark-dark-96.png' : 'plume-mark-white-96.png';
      await expect(link.locator(`img[src$="${shown}"]`)).toBeVisible();
      await expect(link.locator(`img[src$="${hidden}"]`)).toBeHidden();
      await expect
        .poll(() =>
          link.locator(`img[src$="${shown}"]`).evaluate((el: HTMLImageElement) => el.naturalWidth),
        )
        .toBeGreaterThan(0);
      expect((await link.locator(`img[src$="${shown}"]`).boundingBox())?.width).toBeGreaterThan(24);
      await expect(page.locator('link[rel="icon"][href="/plume-favicon-32.png"]')).toHaveCount(1);
      await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
        'href',
        '/plume-apple-touch-icon.png',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-header', theme);
    });
  });
}

test('on a narrow screen the control box starts closed and the detail stacks under the graph', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(SMALL);
  await expect(page.getByRole('button', { name: /Filter and mappings/ })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  const c = await boxOf(page.getByRole('group', { name: /Mapping graph/ }));
  const d = await boxOf(page.getByRole('region', { name: 'Mapping detail' }));
  expect(d.y).toBeGreaterThanOrEqual(c.y + c.height - 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
