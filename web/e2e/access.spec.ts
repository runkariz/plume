import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** Who sees which model: official list, unlisted share page with lineage, unreleased review, server generation. */
const TOKEN = 'pl_e2e_token_value';
const UNLISTED_V3 = 'u-3f9a0c71d2e84b5f9a6c1d7e8b2a4c60';
const DEMO_KEY = 'ok-demo-3f9a0c71d2e84b5f';

async function signInThenModels(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Models', exact: true }).click(); // in-app: the token lives in memory
}

async function suggestions(page: Page) {
  await page.getByRole('checkbox', { name: /Shopify/ }).check({ force: true });
  await page.getByRole('checkbox', { name: /WooCommerce/ }).check({ force: true });
  await page.getByRole('checkbox', { name: /Mirakl/ }).check({ force: true });
  await page.getByRole('button', { name: 'Suggest models →' }).click();
  await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`model access (${theme})`, () => {
    test.use({ theme });

    test('the Models list: Official only; "Your models" from this browser', async ({ page }) => {
      await page.addInitScript(
        (k) => localStorage.setItem('plume-owner-keys', JSON.stringify([k])),
        DEMO_KEY,
      );
      await page.goto('/models');
      const official = page.getByRole('region', { name: 'Official models' });
      await expect(official.getByText('Official').first()).toBeVisible();
      await expect(official.getByText(/returns count/)).toHaveCount(0);
      const mine = page.getByRole('region', { name: 'Your models' });
      await expect(mine.getByText('v3 of 3')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-models-list', theme);
    });

    test('an unlisted model: share link, lineage, Modify with Claude', async ({ page }) => {
      await page.goto(`/models/${UNLISTED_V3}`);
      await expect(page.getByRole('region', { name: 'Share this model' })).toBeVisible();
      await expect(page.locator('.lineage')).toContainText('v3 of 3');
      await expect(page.getByRole('region', { name: 'Modify with Claude' })).toBeVisible();
      await page.getByText(/^Versions of this model/).click();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-unlisted-model', theme);
    });

    test('an unreleased model is reviewed and released by a signed-in maintainer', async ({
      page,
    }) => {
      await signInThenModels(page);
      await page
        .getByRole('region', { name: 'Waiting for review' })
        .getByRole('link', { name: 'Return' })
        .click();
      await expect(page.getByText('Unreleased: waiting for your review')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-unreleased-review', theme);
      await page.getByRole('button', { name: 'Release' }).click();
      await expect(page.locator('.chip', { hasText: 'Official' })).toBeVisible();
      await shot(page, 'w12-released', theme);
    });

    test('server generation: a failed job shows its rounds; no model key (503) offers Claude', async ({
      page,
    }) => {
      await signInThenModels(page);
      await suggestions(page);
      await page.getByRole('button', { name: 'Generate Customer', exact: true }).click();
      const panel = page.getByRole('region', { name: 'Generation on the server' });
      await expect(panel.getByText(/No accepted draft after 3 rounds/)).toBeVisible();
      await expect(panel.getByText('refused, 1 issue').first()).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-job-failed', theme);
      await panel.getByRole('button', { name: 'Close' }).click();
      await page.getByRole('button', { name: 'Generate Refund', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('not configured');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-generate-503', theme);
    });

    test('signed out: Claude session, a pasted draft is stored unlisted with its owner key', async ({
      page,
    }) => {
      await page.goto('/models');
      await suggestions(page);
      await page.getByRole('button', { name: 'Generate Shipment', exact: true }).click();
      const panel = page.getByRole('region', { name: 'Generation session' });
      await expect(panel.getByText('Stored unlisted: only people with the link.')).toBeVisible();
      await panel
        .getByLabel('Draft JSON')
        .fill(JSON.stringify({ name: 'Shipment', fields: [{ name: 'carrier' }] }));
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Shipment' })).toBeVisible();
      await expect(page.getByText('Your model is saved, and unlisted')).toBeVisible();
      await expect(page.getByRole('region', { name: 'Share this model' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w12-anonymous-created', theme);
    });
  });
}

test('a failed server generation is announced next to the concept that was clicked, in view (owner bug)', async ({
  page,
}) => {
  // sign in through the real sign-in flow, then move around inside the app (the token lives in memory only)
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Models', exact: true }).click();
  await suggestions(page);
  // "Refund" is far down the page of 24 concepts: its message used to appear above the list, out of sight
  const row = page.getByRole('article', { name: 'Refund', exact: true });
  await row.scrollIntoViewIfNeeded();
  await row.getByRole('button', { name: 'Generate Refund', exact: true }).click();
  const alert = page.getByRole('alert').filter({ hasText: 'not configured' });
  await expect(alert).toBeVisible();
  await expect(alert).toBeInViewport();
  // next to the concept, not at the top of the page
  const [r, a] = await Promise.all([row.boundingBox(), alert.boundingBox()]);
  expect(Math.abs((a?.y ?? 0) - ((r?.y ?? 0) + (r?.height ?? 0)))).toBeLessThan(400);
  await expect(alert.getByRole('button', { name: 'Use Claude instead' })).toBeVisible();
});

test('a page refresh keeps the maintainer signed in; Sign out ends it; it stays out of the URL and localStorage', async ({
  page,
}) => {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  // a refresh (a full page load) does not sign the person out
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  // a new page in the same tab too, and maintainer pages open without the sign-in form
  await page.goto('/models');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  // where the token is: sessionStorage only
  const stored = await page.evaluate(() => ({
    local: JSON.stringify({ ...localStorage }),
    session: Object.keys(sessionStorage),
    url: window.location.href,
  }));
  expect(stored.local).not.toContain(TOKEN);
  expect(stored.url).not.toContain(TOKEN);
  expect(stored.session).toContain('plume-maintainer-session');
  // Sign out ends it, also after a refresh
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(sessionStorage))).not.toContain(
    'plume-maintainer-session',
  );
});
