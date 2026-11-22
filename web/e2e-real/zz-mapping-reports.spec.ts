import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Mapping reports on the real API: a reader's LLM reports a wrong mapping of a canonical model through MCP
 * (report_mapping), the validator keeps or refuses the suggestion, the maintainer accepts it in the web app and it becomes
 * a verified mapping that find_mapping_reports shows. Fixtures only (shopify-mini). Needs PLUME_REPORTS=on on a fresh
 * stack: PLUME_E2E_REPORTS=true. Run it ALONE: it creates the reports it reads.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const MCP = process.env.PLUME_E2E_MCP_URL ?? 'http://127.0.0.1:18481/mcp';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const ON = process.env.PLUME_E2E_REPORTS === 'true';
const DOC = 'endpoint:GET~/admin/api/{version}/products.json';
// the quote must be the field's own description line in the document (the validator checks it is about the field)
const QUOTE = 'Name of the product.';
const PROBLEM_OK = 'The product title is mapped to the body text instead of the title field.';
const PROBLEM_BAD = 'The product sku is mapped to the wrong field.';
const PROBLEM_ABSENT = 'The product subtitle is mapped to body_html, but Shopify has no subtitle.';
// the body_html field's own description line, which is what proves it is not the subtitle
const QUOTE_BODY = 'Description of the product, formatted in HTML.';
const auth = { Authorization: `Bearer ${TOKEN}` };

/** One MCP tool call over streamable HTTP, in its own session: the real structuredContent. */
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
      clientInfo: { name: 'mapping-report-check', version: '1' },
    },
  });
  await send({ jsonrpc: '2.0', method: 'notifications/initialized' }, init.session);
  const r = await send(
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name, arguments: args } },
    init.session,
  );
  return r.json?.result as { structuredContent: Record<string, unknown> };
}

type MReport = {
  id: string;
  canonicalField: string;
  status: string;
  validation?: { ok: boolean; reason?: string | null } | null;
  suggestion?: unknown;
  reportCount: number;
};

async function reports(request: APIRequestContext) {
  return (await (
    await request.get(`${API}/v1/maintainer/mapping-reports`, { headers: auth })
  ).json()) as { reports: MReport[]; enabled?: boolean };
}

async function seed(request: APIRequestContext) {
  if ((await reports(request)).reports.length > 0) return;
  const session = (await (
    await request.post(`${API}/v1/models/generate`, {
      data: { apis: ['shopify', 'woocommerce'], concept: 'Product' },
    })
  ).json()) as { sessionId: string };
  // a suggestion that validates: a real field of the products endpoint and a quote from its document
  await mcp(request, 'report_mapping', {
    user_consent: 'asked_and_approved',
    model: session.sessionId,
    api: 'shopify',
    canonical_field: 'title',
    kind: 'wrong',
    problem: PROBLEM_OK,
    current_mapping: 'products[].body_html',
    suggested_mapping: {
      paths: ['products[].title'],
      evidence: [{ doc_id: DOC, quote: QUOTE }],
    },
  });
  // the same field and kind from another session: a note on the first report (count 2)
  await mcp(request, 'report_mapping', {
    user_consent: 'asked_and_approved',
    model: session.sessionId,
    api: 'shopify',
    canonical_field: 'title',
    kind: 'wrong',
    problem: PROBLEM_OK,
  });
  // a suggestion that fails the validator: the field is not in the package
  await mcp(request, 'report_mapping', {
    user_consent: 'asked_and_approved',
    model: session.sessionId,
    api: 'shopify',
    canonical_field: 'sku',
    kind: 'wrong',
    problem: PROBLEM_BAD,
    suggested_mapping: {
      paths: ['products[].no_such_field'],
      evidence: [{ doc_id: DOC, quote: QUOTE }],
    },
  });
  // an absence: the field is not available on the API, and must not be mapped from body_html
  await mcp(request, 'report_mapping', {
    user_consent: 'asked_and_approved',
    model: session.sessionId,
    api: 'shopify',
    canonical_field: 'subtitle',
    kind: 'wrong',
    problem: PROBLEM_ABSENT,
    current_mapping: 'products[].body_html',
    suggested_mapping: {
      notAvailable: true,
      notFrom: ['products[].body_html'],
      evidence: [{ doc_id: DOC, quote: QUOTE_BODY }],
    },
  });
}

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Reported questions' }).first().click();
  await page
    .getByRole('navigation', { name: 'Kinds of reports' })
    .getByRole('link', { name: 'Mapping reports' })
    .click();
}

test.describe.configure({ mode: 'serial' });

for (const theme of THEMES) {
  test.describe(`mapping reports, real data (${theme})`, () => {
    test.skip(!ON, 'set PLUME_E2E_REPORTS=true with PLUME_REPORTS=on on a fresh stack');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the list: the merged report first, the failed suggestion marked', async ({
      page,
      request,
    }) => {
      await seed(request);
      const list = await reports(request);
      expect(list.enabled).toBe(true);
      expect((list.reports[0] as { consentMethod?: string }).consentMethod).toBe('llm_attested');
      expect(list.reports[0]?.canonicalField).toBe('title'); // most reported first
      expect(list.reports[0]?.reportCount).toBe(2);
      const bad = list.reports.find((r) => r.canonicalField === 'sku');
      expect(bad?.validation?.ok).toBe(false);
      expect(bad?.suggestion ?? null).toBeNull(); // never stored
      await signIn(page);
      const rows = page.getByRole('list', { name: 'Mapping reports' }).getByRole('listitem');
      await expect(rows).toHaveCount(3);
      await expect(rows.first()).toContainText('title');
      await expect(rows.first()).toContainText('2 reports');
      await expect(rows.first()).toContainText('consent: assistant attested');
      await expect(rows.first()).toContainText('suggestion valid');
      await expect(rows.filter({ hasText: 'sku' })).toContainText('suggestion failed');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w51-real-mapping-list', theme);
    });

    test('a report: current against suggested, the quote marked in the document, the validator', async ({
      page,
    }) => {
      await signIn(page);
      await page.getByRole('list', { name: 'Mapping reports' }).getByRole('link').first().click();
      const compare = page.getByRole('region', { name: 'Current and suggested mapping' });
      await expect(compare.getByRole('region', { name: 'Current mapping' })).toContainText(
        'body_html',
      );
      await expect(
        compare.getByRole('region', { name: 'Suggested mapping', exact: true }),
      ).toContainText('products[].title');
      await expect(compare.locator('mark')).toContainText(QUOTE);
      await expect(compare.getByRole('group', { name: 'Validator result' })).toContainText(
        'Passed the validator',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w51-real-mapping-report', theme);
    });

    test('a verified absence: "Not available on shopify", what it is not from, the quote marked', async ({
      page,
    }) => {
      await signIn(page);
      await page
        .getByRole('list', { name: 'Mapping reports' })
        .getByRole('link', { name: /subtitle/ })
        .click();
      const suggested = page.getByRole('region', { name: 'Suggested mapping', exact: true });
      await expect(suggested).toContainText('Not available on shopify');
      await expect(suggested).toContainText('products[].body_html');
      await expect(
        page.getByRole('region', { name: 'Current and suggested mapping' }).locator('mark'),
      ).toContainText(QUOTE_BODY);
      await expect(page.getByRole('group', { name: 'Validator result' })).toContainText(
        'Passed the validator',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(
        page.getByRole('region', { name: 'Current and suggested mapping' }),
        'w51-real-mapping-absence',
        theme,
      );
    });

    test('the failed one shows the validator reason and cannot be accepted', async ({ page }) => {
      await signIn(page);
      await page
        .getByRole('list', { name: 'Mapping reports' })
        .getByRole('link', { name: /sku/ })
        .click();
      const validator = page.getByRole('group', { name: 'Validator result' });
      await expect(validator).toContainText('Failed the validator');
      await expect(validator).toContainText(/FIELD_NOT_FOUND|not/i);
      await page.getByRole('form', { name: 'Decide' }).getByLabel('Reason').fill('check');
      await expect(
        page.getByRole('form', { name: 'Decide' }).getByRole('button', { name: 'Accept' }),
      ).toBeDisabled();
      await shotOf(
        page.getByRole('region', { name: 'Current and suggested mapping' }),
        'w51-real-mapping-failed',
        theme,
      );
    });
  });
}

test.describe('deciding on the real API', () => {
  test.skip(!ON, 'set PLUME_E2E_REPORTS=true with PLUME_REPORTS=on on a fresh stack');

  test('accepting makes a verified mapping that readers see', async ({ page, request }) => {
    await seed(request);
    const target = (await reports(request)).reports.find((r) => r.canonicalField === 'title');
    expect(target?.status).toBe('open');
    await signIn(page);
    await page.getByRole('list', { name: 'Mapping reports' }).getByRole('link').first().click();
    const decide = page.getByRole('form', { name: 'Decide' });
    await decide.getByLabel('Reason').fill('The title field is the product title.');
    await decide.getByRole('button', { name: 'Accept' }).click();
    await expect(decide.getByText('Accepted: it is now a verified mapping.')).toBeVisible();
    await expect(page.getByRole('region', { name: 'Verified mapping' })).toContainText(
      `verified (user report ${target?.id})`,
    );
    const verified = (await (
      await request.get(`${API}/v1/maintainer/verified-mappings?api=shopify`, { headers: auth })
    ).json()) as { mappings: { reportId: string; canonicalField: string; suspended: boolean }[] };
    expect(verified.mappings.some((m) => m.reportId === target?.id && !m.suspended)).toBe(true);
    // readers see the verified mapping when they look for reports on that field
    const session = (await (
      await request.post(`${API}/v1/models/generate`, {
        data: { apis: ['shopify', 'woocommerce'], concept: 'Product' },
      })
    ).json()) as { sessionId: string };
    const found = await mcp(request, 'find_mapping_reports', {
      model: session.sessionId,
      api: 'shopify',
      field: 'title',
    });
    expect(JSON.stringify(found.structuredContent)).toContain('products[].title');
    await page.goto('/maintainer/mapping-reports?status=accepted');
    await expect(page.getByRole('list', { name: 'Mapping reports' })).toContainText('verified');
  });
});
