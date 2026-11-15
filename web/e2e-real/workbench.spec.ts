import { expect, type APIRequestContext } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from '../e2e/helpers';

/**
 * The model graph's control box and detail panel, and the header mark, against the real API. It takes the first
 * official model the stack has (models.spec.ts releases one), so run the whole real project, not this file alone,
 * on a fresh stack.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';

interface Model {
  id: string;
  name: string;
  inputs: { id: string; shortName: string }[];
  fields: { name: string; support: Record<string, string> }[];
}
async function officialModel(request: APIRequestContext): Promise<Model> {
  const list = (await (await request.get(`${API}/v1/models`)).json()) as {
    items: { id: string }[];
  };
  const first = list.items[0];
  expect(first, 'an official model exists (released by models.spec.ts)').toBeTruthy();
  return (await (await request.get(`${API}/v1/models/${first?.id}`)).json()) as Model;
}

for (const theme of THEMES) {
  test.describe(`real model workbench (${theme})`, () => {
    test.use({ theme, viewport: { width: 1440, height: 900 } });

    test('control box, detail panel and API focus on a real model', async ({ page, request }) => {
      const model = await officialModel(request);
      const names = model.inputs.map((a) => a.shortName);
      expect(names.length).toBeGreaterThanOrEqual(2);
      await page.goto(`/models/${model.id}?view=graph&scope=all`);
      const canvas = page.getByRole('group', { name: /Mapping graph/ });
      await expect(canvas).toBeVisible();
      await expect(page.locator('.react-flow__node-canonical')).toHaveCount(model.fields.length);
      // the detail is beside the graph, in the first screen, and shows a real mapping
      const detail = page.getByRole('region', { name: 'Mapping detail' });
      await expect(detail.getByRole('heading')).toContainText(' ← ');
      const d = await detail.boundingBox();
      expect((d?.y ?? 9999) + 120).toBeLessThan(900);
      const box = page.getByRole('complementary', { name: 'Graph controls' });
      await expect(box.getByRole('listbox', { name: 'Mappings' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-real-graph', theme);

      // focus on the second API only: the first is greyed out, nothing is removed, the URL keeps it
      const total = await page.locator('.react-flow__node').count();
      const [firstApi, secondApi] = model.inputs;
      await box.getByRole('checkbox', { name: firstApi?.shortName ?? '' }).click();
      for (const other of model.inputs.slice(2))
        await box.getByRole('checkbox', { name: other.shortName }).click();
      await expect(page).toHaveURL(new RegExp(`show=${secondApi?.id}`));
      await expect(page.locator('.react-flow__node.dim').first()).toBeAttached();
      expect(await page.locator('.react-flow__node').count()).toBe(total);
      await expect(page.locator('.react-flow__edge.dim').first()).toBeAttached();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-real-graph-api-focus', theme);

      // pick a mapping from the list: it is selected, in the URL, and the detail follows
      const option = box.getByRole('option').nth(1);
      const label = (await option.locator('.wb-row-name').textContent()) ?? '';
      await option.click();
      await expect(detail.getByRole('heading')).toContainText(label);
      await expect(page).toHaveURL(/field=/);
      await page.reload();
      await expect(
        page.getByRole('checkbox', { name: firstApi?.shortName ?? '' }),
      ).not.toBeChecked();
      await expect(detail.getByRole('heading')).toContainText(label);
    });

    test('selected field: the view fits the selection', async ({ page, request }) => {
      const model = await officialModel(request);
      await page.goto(`/models/${model.id}?view=graph&scope=field`);
      await expect(page.locator('.react-flow__node-canonical')).toHaveCount(1);
      const canvas = await page.getByRole('group', { name: /Mapping graph/ }).boundingBox();
      const controls = await page
        .getByRole('complementary', { name: 'Graph controls' })
        .boundingBox();
      await expect
        .poll(async () => {
          for (const n of await page
            .locator('.react-flow__node-canonical, .react-flow__node-apiField')
            .all()) {
            const b = await n.boundingBox();
            if (!b || !canvas || !controls) return 'no box';
            if (b.x < controls.x + controls.width - 2) return 'under the control box';
            if (b.x + b.width > canvas.x + canvas.width + 2) return 'outside the canvas';
          }
          return 'fits';
        })
        .toBe('fits');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-real-graph-selected-field', theme);
    });

    test('the header shows the brand mark of this theme', async ({ page }) => {
      await page.goto('/');
      const link = page.getByRole('link', { name: 'Plume home' });
      const shown = theme === 'dark' ? 'plume-mark-white-96.png' : 'plume-mark-dark-96.png';
      await expect(link.locator(`img[src$="${shown}"]`)).toBeVisible();
      await expect
        .poll(() =>
          link.locator(`img[src$="${shown}"]`).evaluate((el: HTMLImageElement) => el.naturalWidth),
        )
        .toBeGreaterThan(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w14-real-header', theme);
    });
  });
}
