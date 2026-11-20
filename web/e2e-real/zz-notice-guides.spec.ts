import { expect } from '@playwright/test';
import { expectNoSeriousA11y, settle, shotOf, test, THEMES } from '../e2e/helpers';

/**
 * The guides a notice names (`docIds`), linked on the auth section, on real packages: Kaufland (3 guides),
 * AliExpress (4) and Metro Markets (4). Needs those packages loaded (one `load` each): PLUME_E2E_NOTICE_GUIDES=true.
 */
const API = process.env.PLUME_E2E_API_URL ?? 'http://127.0.0.1:18480';
const ON = process.env.PLUME_E2E_NOTICE_GUIDES === 'true';

type Notice = { code: string; docIds?: string[] };

for (const theme of THEMES) {
  test.describe(`notice guides, real data (${theme})`, () => {
    test.skip(
      !ON,
      'set PLUME_E2E_NOTICE_GUIDES=true with kaufland, aliexpress and metromarkets loaded',
    );
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    for (const api of ['kaufland', 'aliexpress', 'metromarkets']) {
      test(`${api}: each guide of the auth notice is a link titled with the guide's title`, async ({
        page,
        request,
      }) => {
        const body = (await (await request.get(`${API}/v1/apis/${api}/auth`)).json()) as {
          notices: Notice[];
        };
        const notice = body.notices.find((n) => (n.docIds?.length ?? 0) > 0);
        expect(notice, 'the package has an auth notice that names guides').toBeDefined();
        const ids = notice?.docIds ?? [];
        await page.goto(`/apis/${api}?section=auth`);
        const card = page.getByRole('region', { name: 'Authentication' });
        const guides = card.getByRole('list', { name: `Guides for this note (${notice?.code})` });
        await expect(guides.getByRole('link')).toHaveCount(ids.length);
        // titles replace the ids (a guide whose title did not arrive keeps its id: none here)
        await expect
          .poll(
            async () =>
              (await guides.getByRole('link').allTextContents()).filter((t) =>
                t.startsWith('guide:'),
              ).length,
          )
          .toBe(0);
        await settle(page);
        await expectNoSeriousA11y(page);
        await shotOf(card, `w40-real-${api}-notice-guides`, theme);
        await guides.getByRole('link').first().click();
        await expect(page).toHaveURL(new RegExp(`/apis/${api}/documents/guide%3A`));
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      });
    }
  });
}
