import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { hostPage, realOrder, widgetHtml } from './widget-host';
/** The plain Playwright test: the shared fixture injects a localStorage script into every frame, which a sandboxed frame forbids. */
const THEMES = ['light', 'dark'] as const;

/**
 * The model view as an MCP App: the BUILT single file (npm run build:widget) in a sandboxed iframe under the default
 * CSP with the network cut, driven by a stand-in host. Needs dist-widget/widget.html.
 */
const SHOTS = process.env.PLUME_E2E_SHOTS_DIR;
const order = realOrder();
// as MCP results are shaped: the inputs carry no logo (only the HTTP routes add one)
const mcpInputs = (order.inputs as Record<string, unknown>[]).map((a) =>
  Object.fromEntries(Object.entries(a).filter(([k]) => k !== 'logo')),
);
const small = {
  ...order,
  inputs: mcpInputs,
  fields: (order.fields as unknown[]).slice(0, 5),
  visibility: 'unlisted',
  lineage: { id: 'L', version: 3, versions: 3, basedOn: 'u-prev', latestId: 'u-1', history: [] },
};
const asResult = (structuredContent: unknown) => ({
  content: [{ type: 'text', text: 'Model summary (text fallback)' }],
  structuredContent,
});

async function open(
  page: Page,
  theme: 'light' | 'dark',
  result: unknown,
  extra: { width?: number; openLinks?: boolean } = {},
) {
  const problems: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') problems.push(`${m.type()}: ${m.text()}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  // nothing may leave the machine: only the page itself and data: URLs
  await page.route('**/*', (route) => {
    const u = route.request().url();
    if (u.startsWith('about:') || u.startsWith('data:') || u.startsWith('blob:'))
      return route.continue();
    problems.push(`request: ${u}`);
    return route.abort();
  });
  await page.setContent(hostPage({ widget: widgetHtml(), theme, result, ...extra }));
  const frame = page.frameLocator('#app');
  return { frame, problems };
}

for (const theme of THEMES) {
  test.describe(`model view widget (${theme})`, () => {
    test('big model: the graph on one field, the control box and the detail; no network, no console errors; sized by the host', async ({
      page,
    }) => {
      const { frame, problems } = await open(
        page,
        theme,
        asResult({ ...order, visibility: 'official' }),
        {
          openLinks: true,
        },
      );
      await expect(frame.getByRole('heading', { name: 'Order', level: 1 })).toBeVisible();
      await expect(frame.getByText('Official', { exact: true })).toBeVisible();
      await expect(frame.getByRole('group', { name: /Mapping graph/ })).toBeVisible();
      await expect(frame.getByRole('region', { name: 'Mapping detail' })).toBeVisible();
      await expect(frame.getByRole('complementary', { name: 'Graph controls' })).toBeVisible();
      await expect(frame.locator('.react-flow__node-canonical')).toHaveCount(1); // big: Selected field first
      // the host applies the theme
      await expect(frame.locator('html')).toHaveAttribute('data-theme', theme);
      // the frame is as tall as the view says
      await expect
        .poll(() =>
          page.evaluate(() => (window as unknown as { __sizes: number[] }).__sizes.at(-1) ?? 0),
        )
        .toBeGreaterThan(300);
      const h = await page.locator('#app').evaluate((el) => (el as HTMLIFrameElement).clientHeight);
      const reported = await page.evaluate(
        () => (window as unknown as { __sizes: number[] }).__sizes.at(-1) ?? 0,
      );
      expect(Math.abs(h - (reported + 2))).toBeLessThan(4);
      // working inside the sandbox: open the control box (closed in a narrow frame), pick a mapping, the detail follows
      await frame.getByRole('button', { name: /Filter and mappings/ }).click();
      // pick a mapping from the list (the box scrolls on its own when the frame is short)
      await frame.getByRole('option').nth(2).click();
      await expect(
        frame.getByRole('region', { name: 'Mapping detail' }).getByRole('heading'),
      ).toBeVisible();
      // nothing in the console (a CSP violation would show here); read BEFORE axe, which injects itself into the frame
      expect(problems).toEqual([]);
      // axe, inside the frame
      const { violations } = await new AxeBuilder({ page }).analyze();
      expect(
        violations
          .filter((v) => v.impact === 'serious' || v.impact === 'critical')
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`),
      ).toEqual([]);
      if (SHOTS) {
        mkdirSync(SHOTS, { recursive: true });
        await page.screenshot({ path: join(SHOTS, `w15-widget-big-${theme}.png`), fullPage: true });
      }
    });

    test('a save without a token: "Your models" link with Copy, in the sandboxed frame; nothing is stored or requested', async ({
      page,
    }) => {
      const URL_ = 'https://plume.example/mine/c-E2eCollection0123456789';
      const { frame, problems } = await open(
        page,
        theme,
        asResult({
          accepted: true,
          created: true,
          collection: { id: 'c-E2eCollection0123456789', url: URL_, created: true },
          share_url: 'https://plume.example/models/u-1',
          model: small,
        }),
        { openLinks: true, width: 560 },
      );
      const notice = frame
        .getByRole('status')
        .filter({ hasText: 'Your model is saved, and unlisted' });
      await expect(notice).toBeVisible();
      await expect(notice).toContainText('Your models:');
      await expect(frame.getByLabel('Link to My models')).toHaveValue(URL_);
      // the sandbox may or may not allow the clipboard: either way the person is told what happened
      await frame.getByRole('button', { name: 'Copy link' }).click();
      await expect(notice.getByRole('status')).toHaveText(
        /Link copied|Copy failed: the link is selected/,
      );
      // opening it goes through the host
      await frame.getByRole('button', { name: 'Open My models' }).click();
      await expect
        .poll(() => page.evaluate(() => (window as unknown as { __opened: string[] }).__opened))
        .toContain(URL_);
      const { violations } = await new AxeBuilder({ page }).analyze();
      expect(
        violations
          .filter((v) => v.impact === 'serious' || v.impact === 'critical')
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`),
      ).toEqual([]);
      if (SHOTS) {
        mkdirSync(SHOTS, { recursive: true });
        await page.screenshot({
          path: join(SHOTS, `w21-widget-my-models-${theme}.png`),
          fullPage: true,
        });
      }
      await frame.getByRole('button', { name: 'Dismiss' }).click();
      await expect(frame.getByLabel('Link to My models')).toHaveCount(0);
      expect(problems).toEqual([]);
    });

    test('small unlisted model: lineage, whole graph, "Open in Plume" goes through the host', async ({
      page,
    }) => {
      const { frame, problems } = await open(
        page,
        theme,
        asResult({ accepted: true, share_url: 'https://plume.example/models/u-1', model: small }),
        { openLinks: true, width: 560 },
      );
      await expect(frame.getByRole('heading', { name: 'Order', level: 1 })).toBeVisible();
      await expect(frame.getByText('v3 of 3')).toBeVisible();
      await expect(frame.getByText('Unlisted: anyone with the link')).toBeVisible();
      await expect(frame.locator('.react-flow__node-canonical')).toHaveCount(5);
      await frame.getByRole('button', { name: 'Open in Plume' }).click();
      await expect
        .poll(() => page.evaluate(() => (window as unknown as { __opened: string[] }).__opened))
        .toEqual(['https://plume.example/models/u-1']);
      // a compact layout for a chat column: nothing scrolls sideways, the detail sits under the graph
      const overflow = await frame
        .locator('html')
        .evaluate((el) => el.scrollWidth - el.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      const g = await frame.getByRole('group', { name: /Mapping graph/ }).boundingBox();
      const d = await frame.getByRole('region', { name: 'Mapping detail' }).boundingBox();
      expect((d?.y ?? 0) + 1).toBeGreaterThanOrEqual((g?.y ?? 0) + (g?.height ?? 0));
      if (SHOTS)
        await page.screenshot({
          path: join(SHOTS, `w15-widget-small-${theme}.png`),
          fullPage: true,
        });
      expect(problems).toEqual([]);
    });

    test('a host without openLinks: the link is shown as text; a refused draft shows why', async ({
      page,
    }) => {
      const a = await open(
        page,
        theme,
        asResult({ accepted: true, share_url: 'https://plume.example/models/u-1', model: small }),
      );
      await expect(a.frame.getByText('https://plume.example/models/u-1')).toBeVisible();
      await expect(a.frame.getByRole('button', { name: 'Open in Plume' })).toHaveCount(0);
      await page.reload();
    });

    test('the host can change the theme while the view is open', async ({ page }) => {
      const { frame } = await open(page, theme, asResult(small));
      const other = theme === 'dark' ? 'light' : 'dark';
      await expect(frame.locator('html')).toHaveAttribute('data-theme', theme);
      await page.evaluate(
        (t) =>
          (window as unknown as { __send: (m: unknown) => void }).__send({
            jsonrpc: '2.0',
            method: 'ui/notifications/host-context-changed',
            params: { theme: t },
          }),
        other,
      );
      await expect(frame.locator('html')).toHaveAttribute('data-theme', other);
    });

    test('a model set: the diagram and the text, no console errors, axe clean', async ({
      page,
    }) => {
      const apis = [
        { id: 'shopify', name: 'Shopify', shortName: 'Shopify', build: 'b-1' },
        { id: 'woocommerce', name: 'WooCommerce', shortName: 'WooCommerce', build: 'b-2' },
      ];
      const cov = (a: number, b: number, t: number) => ({
        shopify: { mapped: a, total: t },
        woocommerce: { mapped: b, total: t },
      });
      const set = {
        kind: 'model_set',
        id: 'set_x',
        name: 'Shop',
        visibility: 'official',
        official: true,
        generatedAt: '2026-11-16T10:00:00Z',
        inputs: apis,
        members: [
          {
            concept: 'Order',
            modelId: 'm-order',
            name: 'Order',
            fieldCount: 12,
            coverage: cov(9, 11, 12),
            visibility: 'official',
            version: 1,
          },
          {
            concept: 'Product',
            modelId: 'm-product',
            name: 'Product',
            fieldCount: 14,
            coverage: cov(14, 13, 14),
            visibility: 'official',
            version: 1,
          },
          { concept: 'Variant', modelId: 'm-variant', missing: true },
        ],
        relations: [
          {
            id: 'order-items',
            from: 'Order',
            to: 'Product',
            kind: 'embedded',
            cardinality: '1:n',
            embed: { field: 'items' },
            ref: null,
            confirmed: true,
            support: { shopify: 'nested', woocommerce: 'nested' },
            sources: {},
          },
          {
            id: 'product-variants',
            from: 'Product',
            to: 'Variant',
            kind: 'reference',
            cardinality: 'n:1',
            embed: null,
            ref: null,
            confirmed: false,
            support: { shopify: 'sub_resource', woocommerce: null },
            sources: {},
          },
        ],
        undecided: ['product-variants'],
        openQuestions: [],
        sharePath: '/model-sets/set_x',
      };
      const { frame, problems } = await open(
        page,
        theme,
        asResult({ accepted: true, share_url: 'https://plume.example/model-sets/set_x', set }),
        { openLinks: true },
      );
      await expect(frame.getByRole('heading', { name: 'Shop', level: 1 })).toBeVisible();
      await expect(frame.locator('.react-flow__node-member')).toHaveCount(3);
      // the control box and the detail: pick the proposal in the list
      await frame.getByRole('button', { name: /Filter models and relations/ }).click();
      await frame
        .getByRole('listbox', { name: 'Models and relations' })
        .getByRole('option', { name: /Product → Variant/ })
        .click();
      const detail = frame.getByRole('region', { name: 'Selected model or relation' });
      await expect(detail.getByRole('heading', { name: 'Product → Variant' })).toBeVisible();
      await expect(detail.getByText('Proposal: to decide')).toBeVisible();
      await expect(detail.getByText(/open the set in Plume to pick how/)).toBeVisible();
      await expect(detail.getByRole('radio')).toHaveCount(0);
      // the same as text, for hosts and screen readers
      await frame.getByText('The models and relations as text').click();
      await expect(
        frame.getByRole('region', { name: 'Relations' }).getByText('Order → Product'),
      ).toBeVisible();
      await expect(frame.getByText('1 to decide').first()).toBeVisible();
      await frame.getByRole('button', { name: 'Open in Plume' }).click();
      await expect
        .poll(() => page.evaluate(() => (window as unknown as { __opened: string[] }).__opened))
        .toEqual(['https://plume.example/model-sets/set_x']);
      const overflow = await frame
        .locator('html')
        .evaluate((el) => el.scrollWidth - el.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      expect(problems).toEqual([]);
      const { violations } = await new AxeBuilder({ page }).analyze();
      expect(
        violations
          .filter((v) => v.impact === 'serious' || v.impact === 'critical')
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`),
      ).toEqual([]);
      if (SHOTS) {
        mkdirSync(SHOTS, { recursive: true });
        await page.screenshot({ path: join(SHOTS, `w17-widget-set-${theme}.png`), fullPage: true });
      }
    });

    test('a refused draft: the issues, nothing stored', async ({ page }) => {
      const { frame, problems } = await open(
        page,
        theme,
        asResult({
          accepted: false,
          issues: [
            {
              code: 'QUOTE_NOT_FOUND',
              field: 'total',
              api: 'shopify',
              message: 'the quote is not in the doc',
            },
          ],
        }),
      );
      await expect(frame.getByText('The draft was refused, nothing was stored')).toBeVisible();
      await expect(frame.getByText('QUOTE_NOT_FOUND')).toBeVisible();
      if (SHOTS)
        await page.screenshot({
          path: join(SHOTS, `w15-widget-refused-${theme}.png`),
          fullPage: true,
        });
      expect(problems).toEqual([]);
    });
  });
}

test('the file on its own (no host) says what it is', async ({ page }) => {
  await page.setContent(widgetHtml());
  await expect(page.getByText(/shown by a Claude app that supports MCP Apps/)).toBeVisible();
});

test('the built file loads nothing remote and keeps everything inline', async () => {
  const html = widgetHtml();
  expect(html).not.toMatch(/<(script|link|img|iframe)[^>]+(src|href)="(?!data:|#)[^"]*"/i);
  expect(html).not.toMatch(/@import|url\(\s*(?!["']?(data:|#))/i);
  expect(html).not.toMatch(/@font-face|font\/woff/); // the host CSP has no font-src: fonts would be blocked
  // the committed file must not depend on who built it: no env variable (name or value), no local address
  expect(html).not.toMatch(/VITE_[A-Z_]+/);
  expect(html).not.toMatch(/127\.0\.0\.1|localhost/);
  expect(html).toContain('ui/initialize');
  expect(Buffer.byteLength(html)).toBeLessThan(3_000_000);
});
