import { expect, type APIRequestContext } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * Reported questions on the real API: reader LLMs report through the MCP tools, the maintainer triages them in the web
 * app. Needs the stack started with PLUME_REPORTS=on (the maintainer token is the usual one): PLUME_E2E_REPORTS=true.
 * Run it ALONE on a fresh stack: it creates the reports it reads.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const MCP = process.env.PLUME_E2E_MCP_URL ?? 'http://127.0.0.1:18481/mcp';
const TOKEN = process.env.PLUME_E2E_TOKEN ?? 'pl_dev_local_web_e2e';
const ON = process.env.PLUME_E2E_REPORTS === 'true';
const Q1 = 'How do I page through every product when page_info rejects the status filter?';
const Q2 = 'Which scope does reading fulfillment orders need?';
const REASON = 'Fulfillment order reads need read_assigned_fulfillment_orders.';

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
      clientInfo: { name: 'report-check', version: '1' },
    },
  });
  await send({ jsonrpc: '2.0', method: 'notifications/initialized' }, init.session);
  const r = await send(
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name, arguments: args } },
    init.session,
  );
  return r.json?.result as { structuredContent: Record<string, unknown> };
}

const auth = { Authorization: `Bearer ${TOKEN}` };

type Report = { id: string; question: string; reportCount: number; status: string };

async function reports(
  request: APIRequestContext,
): Promise<{ reports: Report[]; enabled?: boolean }> {
  return (await (await request.get(`${API}/v1/maintainer/reports`, { headers: auth })).json()) as {
    reports: Report[];
    enabled?: boolean;
  };
}

test.describe.configure({ mode: 'serial' });

for (const theme of THEMES) {
  test.describe(`reported questions, real data (${theme})`, () => {
    test.skip(!ON, 'set PLUME_E2E_REPORTS=true with PLUME_REPORTS=on on a fresh stack');
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('readers report through MCP; the maintainer lists and reads them', async ({
      page,
      request,
    }) => {
      if (!(await reports(request)).reports.some((r) => r.question === Q1)) {
        // the same question from two sessions: one report, a note on it
        await mcp(request, 'report_question', {
          user_consent: 'asked_and_approved',
          api: 'shopify',
          question: Q1,
          what_was_tried: 'search_docs and check_call with page_info',
          what_was_missing: 'which filters work with page_info',
        });
        await mcp(request, 'report_question', {
          user_consent: 'asked_and_approved',
          api: 'shopify',
          question: Q1,
        });
        await mcp(request, 'report_question', {
          user_consent: 'asked_and_approved',
          api: 'shopify',
          question: Q2,
        });
      }
      const list = await reports(request);
      expect(list.enabled).toBe(true);
      const first = list.reports[0];
      expect(first?.question).toBe(Q1); // most reported first
      // the user agreed through the assistant (no elicitation over this raw MCP client)
      expect((list.reports[0] as { consentMethod?: string }).consentMethod).toBe('llm_attested');
      expect(first?.reportCount).toBeGreaterThan(1);

      await page.goto('/maintainer');
      await page.getByLabel('Email').fill('maintainer@example.com');
      await page.getByLabel('Access token').fill(TOKEN);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('link', { name: 'Reported questions' }).click();
      const rows = page.getByRole('list', { name: 'Reports' }).getByRole('listitem');
      await expect(rows.first()).toContainText(Q1);
      await expect(rows.first()).toContainText(`${first?.reportCount} reports`);
      await expect(rows.first()).toContainText('consent: assistant attested');
      await expect(page.getByText('Reported questions are off on this server')).toHaveCount(0);
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w49-real-reports-list', theme);
      await rows.first().getByRole('link').click();
      await expect(page.getByRole('region', { name: 'The report' })).toContainText('page_info');
      await expect(page.getByRole('list', { name: 'Notes on this report' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w49-real-report-detail', theme);
    });
  });
}

test.describe('triage on the real API', () => {
  test.skip(!ON, 'set PLUME_E2E_REPORTS=true with PLUME_REPORTS=on on a fresh stack');

  test('a status with a reason is saved, and readers see the reason of an answered report', async ({
    page,
    request,
  }) => {
    const target = (await reports(request)).reports.find((r) => r.question === Q2);
    expect(target).toBeDefined();
    await page.goto('/maintainer');
    await page.getByLabel('Email').fill('maintainer@example.com');
    await page.getByLabel('Access token').fill(TOKEN);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.getByRole('link', { name: 'Reported questions' }).click();
    await page.getByRole('link', { name: Q2 }).click();
    const form = page.getByRole('form', { name: 'Triage' });
    await form.getByRole('radio', { name: 'Answered' }).click({ force: true });
    await expect(form).toContainText('Readers see this reason');
    await form.getByLabel('Reason').fill(REASON);
    await form.getByRole('button', { name: 'Save status' }).click();
    await expect(form.getByText('Saved.')).toBeVisible();
    const saved = (await (
      await request.get(`${API}/v1/maintainer/reports/${target?.id}`, { headers: auth })
    ).json()) as { status: string; reason: string };
    expect(saved.status).toBe('answered');
    expect(saved.reason).toBe(REASON);
    // the reader tool shows the reason of an answered report
    const found = await mcp(request, 'find_reported_questions', { api: 'shopify', question: Q2 });
    expect(JSON.stringify(found.structuredContent)).toContain(REASON);
    // and the list filter finds it
    await page.goto('/maintainer/reports?status=answered');
    await expect(page.getByRole('list', { name: 'Reports' })).toContainText(Q2);
  });
});

// On a stack with reporting off (the usual one) the maintainer API says enabled: false and the page says so;
// on a stack with it on this test has nothing to look at.
for (const theme of THEMES) {
  test.describe(`reporting off (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('the page says reporting is off', async ({ page, request }) => {
      const { enabled } = await reports(request);
      test.skip(enabled !== false, 'this stack has reporting on');
      await page.goto('/maintainer');
      await page.getByLabel('Email').fill('maintainer@example.com');
      await page.getByLabel('Access token').fill(TOKEN);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('link', { name: 'Reported questions' }).click();
      await expect(page.getByText('Reported questions are off on this server')).toBeVisible();
      await expect(
        page.getByRole('heading', { name: 'Reported questions', level: 1 }),
      ).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(page.locator('main'), 'w49-real-reports-off', theme);
    });
  });
}
