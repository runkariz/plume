import { expect, test as plain, type APIRequestContext } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';
import { hostPage, widgetHtml } from '../e2e/widget-host';

/**
 * How newer docs touch models and sets, against the real API: a model "Order" (mappings that cite the removed
 * DELETE .../notes/{note_id} endpoint) and a model "Receipt" (id and total of model:order, which variant A does not
 * touch) over woocommerce-test + woocommerce, and a set of the two, all saved and released on the kit BASE, then variant A
 * loaded (see web/README.md). Skipped unless PLUME_E2E_IMPACT=true.
 */
const IMPACT = process.env.PLUME_E2E_IMPACT === 'true';
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const MCP = process.env.PLUME_E2E_MCP_URL ?? 'http://127.0.0.1:18481/mcp';

interface Impact {
  status: string;
  affectedCount: number;
  breakingCount: number;
  byMember?: { concept: string; status: string; affectedCount: number }[];
}
interface Listed {
  id: string;
  name: string;
  apis: string[];
  impact?: Impact | null;
}

async function listed(request: APIRequestContext, path: string): Promise<Listed[]> {
  const r = (await (await request.get(`${API}${path}`)).json()) as { items: Listed[] };
  return r.items.filter((x) => x.apis.includes('woocommerce-test'));
}

/** One MCP tool call over streamable HTTP (a session, then tools/call): the real structuredContent. */
async function mcp(request: APIRequestContext, name: string, args: Record<string, unknown>) {
  const headers = {
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
  };
  const send = async (body: object, session?: string) => {
    const res = await request.post(MCP, {
      headers: { ...headers, ...(session ? { 'mcp-session-id': session } : {}) },
      data: body,
    });
    const text = await res.text();
    const data = text.includes('data:')
      ? (
          text
            .split('\n')
            .filter((l) => l.startsWith('data:'))
            .at(-1) ?? ''
        ).slice(5)
      : text;
    return {
      json: data.trim() ? (JSON.parse(data) as { result?: Record<string, unknown> }) : null,
      session: res.headers()['mcp-session-id'],
    };
  };
  const init = await send({
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'check', version: '1' },
    },
  });
  await send({ jsonrpc: '2.0', method: 'notifications/initialized' }, init.session);
  const r = await send(
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name, arguments: args } },
    init.session,
  );
  return r.json?.result as { structuredContent: Record<string, unknown> };
}

plain.skip(!IMPACT, 'needs the impact data set up: PLUME_E2E_IMPACT=true');
test.skip(!IMPACT, 'needs the impact data set up: PLUME_E2E_IMPACT=true');

for (const theme of THEMES) {
  test.describe(`impact on real data (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('lists: Order affected (breaking), Receipt updated but unaffected, the set affected', async ({
      page,
      request,
    }) => {
      const models = await listed(request, '/v1/models');
      const order = models.find((m) => m.name === 'Order');
      const receipt = models.find((m) => m.name === 'Receipt');
      expect(order?.impact?.status).toBe('affected');
      expect(order?.impact?.breakingCount).toBeGreaterThanOrEqual(1);
      expect(receipt?.impact?.status).toBe('updated_unaffected');
      await page.goto('/models');
      const list = page.getByRole('region', { name: 'Official models' });
      const o = list
        .getByRole('link', { name: 'Order', exact: true })
        .first()
        .locator('xpath=ancestor::li');
      await expect(o).toContainText(
        `${order?.impact?.affectedCount} affected (${order?.impact?.breakingCount} breaking)`,
      );
      const r = list
        .getByRole('link', { name: 'Receipt', exact: true })
        .locator('xpath=ancestor::li');
      await expect(r).toContainText('Docs updated, unaffected');
      const sets = page.getByRole('region', { name: 'Official model sets' });
      await expect(sets).toContainText('affected');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(list, 'w26-real-models-list-impact', theme);
      await shotOf(sets, 'w26-real-sets-list-impact', theme);
    });

    test('the Order page leads with the affected mapping, BREAKING, linked to the mapping', async ({
      page,
      request,
    }) => {
      const order = (await listed(request, '/v1/models')).find((m) => m.name === 'Order');
      const full = (await (await request.get(`${API}/v1/models/${order?.id}/impact`)).json()) as {
        affected: { field: string; api: string; change: { breaking: boolean; op: string } }[];
      };
      expect(full.affected.length).toBeGreaterThan(0);
      await page.goto(`/models/${order?.id}`);
      const banner = page.getByTestId('impact-banner');
      await expect(banner).toContainText(`${order?.impact?.affectedCount} mapping`);
      await expect(banner).toContainText('Breaking');
      const first = full.affected[0];
      const rows = banner.getByRole('list', { name: 'Affected mappings' });
      await expect(rows.getByRole('listitem')).toHaveCount(full.affected.length);
      const link = rows.getByRole('link', { name: first?.field ?? '', exact: true }).first();
      await expect(link).toHaveAttribute(
        'href',
        new RegExp(`field=${encodeURIComponent(first?.field ?? '')}`),
      );
      // the stale banner is replaced; no Regenerate for the public
      await expect(page.getByText('This model is built on older docs')).toHaveCount(0);
      await expect(page.getByRole('link', { name: 'Regenerate' })).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(banner, 'w26-real-model-impact-banner', theme);
      // the row leads to the mapping: the field is selected on the page
      await link.click();
      await expect(page).toHaveURL(new RegExp(`field=${encodeURIComponent(first?.field ?? '')}`));
      await shotOf(page.locator('main'), 'w26-real-model-impact-selected', theme);
    });

    test('the Receipt page says updated but unaffected, quietly', async ({ page, request }) => {
      const receipt = (await listed(request, '/v1/models')).find((m) => m.name === 'Receipt');
      await page.goto(`/models/${receipt?.id}`);
      const banner = page.getByTestId('impact-banner');
      await expect(banner).toContainText('Docs updated, your mappings are unaffected');
      await expect(banner).not.toContainText('Breaking');
      await expectNoSeriousA11y(page);
      await shotOf(banner, 'w26-real-receipt-impact-banner', theme);
    });

    test('the set page: the set is affected, its members each have their status, the row names its member', async ({
      page,
      request,
    }) => {
      const set = (await listed(request, '/v1/model-sets'))[0];
      expect(set?.impact?.status).toBe('affected');
      await page.goto(`/model-sets/${set?.id}`);
      const banner = page.getByTestId('impact-banner');
      await expect(banner).toContainText('affected');
      const members = banner.getByRole('list', { name: 'Impact per model' });
      await expect(members).toContainText('Order');
      await expect(members).toContainText('Receipt');
      await expect(members).toContainText('Docs updated, unaffected');
      await expect(banner.getByRole('list', { name: 'Affected mappings' })).toContainText('Order:');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(banner, 'w26-real-set-impact-banner', theme);
    });
  });
}

for (const theme of THEMES) {
  plain.describe(`widget on real MCP results (${theme})`, () => {
    for (const [what, tool, arg, name] of [
      ['Order (affected)', 'get_model', 'snapshot_id', 'Order'],
      ['Receipt (updated, unaffected)', 'get_model', 'snapshot_id', 'Receipt'],
    ] as const)
      plain(
        `${what}: the one-line summary and compact rows, no network`,
        async ({ page, request }) => {
          const models = await listed(request, '/v1/models');
          const id = models.find((m) => m.name === name)?.id as string;
          const result = await mcp(request, tool, { [arg]: id });
          const problems: string[] = [];
          page.on('pageerror', (e) => problems.push(e.message));
          await page.route('**/*', (route) => {
            const u = route.request().url();
            if (u.startsWith('about:') || u.startsWith('data:') || u.startsWith('blob:'))
              return route.continue();
            problems.push(`request: ${u}`);
            return route.abort();
          });
          await page.setViewportSize({ width: 900, height: 900 });
          await page.setContent(hostPage({ widget: widgetHtml(), theme, result, openLinks: true }));
          const frame = page.frameLocator('#app');
          const box = frame.getByTestId('widget-impact');
          if (name === 'Order') {
            await expect(box).toContainText('mapping affected');
            await expect(box).toContainText('Breaking');
            await expect(box.getByRole('listitem').first()).toContainText('removed');
          } else {
            await expect(box).toContainText('Docs updated, your mappings are unaffected');
            await expect(box.getByRole('listitem')).toHaveCount(0);
          }
          // the way on: a button when the server sent the model's link, else its path (no public web url on this stack)
          await expect(
            frame
              .getByRole('button', { name: 'Open in Plume' })
              .or(frame.getByText(/In Plume:/))
              .first(),
          ).toBeVisible();
          expect(problems).toEqual([]);
          const dir = process.env.PLUME_E2E_SHOTS_DIR;
          if (dir)
            await page
              .locator('#app')
              .screenshot({ path: `${dir}/w26-real-widget-${name.toLowerCase()}-${theme}.png` });
        },
      );
  });
}
