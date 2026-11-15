import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, shotOf, test, THEMES } from './helpers';

/** "My models": the link kept in this browser, "Your models" on /models, the /mine page, opening and merging links. */
const DEMO_COLLECTION = 'c-DemoCollection3f9a0c71d2e8';
const SET_COLLECTION = 'c-SetCollection7d1b4a9e0c5f2a';
const DEMO_OWNER_KEY = 'ok-demo-3f9a0c71d2e84b5f';

async function suggestions(page: Page) {
  await page.getByRole('checkbox', { name: /Shopify/ }).check({ force: true });
  await page.getByRole('checkbox', { name: /WooCommerce/ }).check({ force: true });
  await page.getByRole('checkbox', { name: /Mirakl/ }).check({ force: true });
  await page.getByRole('button', { name: 'Suggest models →' }).click();
  await expect(page.getByRole('heading', { name: 'Suggested models' })).toBeVisible();
}

const hold = (page: Page, id: string) =>
  page.addInitScript((v) => localStorage.setItem('plume-collection', v), id);

for (const theme of THEMES) {
  test.describe(`My models (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('"Your models" lists the link this browser holds, with the link to copy', async ({
      page,
    }) => {
      await hold(page, DEMO_COLLECTION);
      await page.goto('/models');
      const mine = page.getByRole('region', { name: 'Your models' });
      await expect(mine.getByText('v3 of 3')).toBeVisible();
      await expect(mine.getByLabel('Link to My models')).toHaveValue(
        new RegExp(`/mine/${DEMO_COLLECTION}$`),
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shotOf(mine, 'w21-your-models', theme);
    });

    test('open another link: a mistyped one is refused, a good one is kept and listed', async ({
      page,
    }) => {
      await page.goto('/models');
      const region = page.getByRole('region', { name: 'Open a My models link' });
      await region.getByText(/Have a My models link/).click();
      await region.getByLabel('My models link').fill('c-NobodyHasThisLink012345');
      await region.getByRole('button', { name: 'Open link' }).click();
      await expect(region.getByRole('alert')).toContainText('does not know that link');
      await region
        .getByLabel('My models link')
        .fill(`https://plume.example/mine/${DEMO_COLLECTION}`);
      await region.getByRole('button', { name: 'Open link' }).click();
      await expect(region.getByRole('status')).toContainText('Opened: 1 item');
      await expect(page.getByRole('region', { name: 'Your models' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      // kept in this browser: a reload still lists it (the mock server forgets nothing it was told in this page, so the
      // link is read from storage only)
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(
        DEMO_COLLECTION,
      );
    });

    test('old owner keys become the link they turned into, once', async ({ page }) => {
      await page.addInitScript(
        (k) => localStorage.setItem('plume-owner-keys', JSON.stringify([k])),
        DEMO_OWNER_KEY,
      );
      await page.goto('/models');
      await expect(
        page.getByRole('region', { name: 'Your models' }).getByText('v3 of 3'),
      ).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(
        DEMO_COLLECTION,
      );
      expect(await page.evaluate(() => localStorage.getItem('plume-owner-keys'))).toBeNull();
    });

    test("the My models page: what is under a link, and merging this browser's other link into it", async ({
      page,
    }) => {
      await hold(page, SET_COLLECTION);
      await page.goto(`/mine/${DEMO_COLLECTION}`);
      await expect(page.getByRole('heading', { level: 1, name: 'My models' })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Models' }).getByText('v3 of 3')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w21-mine-page', theme);
      await page.getByRole('button', { name: 'Merge my other link into this one' }).click();
      await expect(
        page.getByText(/Merged: everything from your other link is here now/),
      ).toBeVisible();
      await expect(
        page
          .getByRole('region', { name: 'Model sets' })
          .getByRole('link', { name: 'Shop (my version)' }),
      ).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(
        DEMO_COLLECTION,
      );
      await shot(page, 'w21-mine-merged', theme);
    });

    test('a link that was merged into another points to it', async ({ page }) => {
      await hold(page, SET_COLLECTION);
      await page.goto(`/mine/${DEMO_COLLECTION}`);
      await page.getByRole('button', { name: 'Merge my other link into this one' }).click();
      await expect(page.getByText(/Merged:/)).toBeVisible();
      // the emptied link, opened inside the app (a reload would reset the mock server)
      await page.getByRole('link', { name: 'Models', exact: true }).first().click();
      await expect(page.getByRole('region', { name: 'Your models' })).toBeVisible();
    });

    test('saving without a token starts the link, shows it once, and a second save joins it silently', async ({
      page,
    }) => {
      await page.goto('/models');
      await suggestions(page);
      await page.getByRole('button', { name: 'Generate Shipment', exact: true }).click();
      let panel = page.getByRole('region', { name: 'Generation session' });
      await panel
        .getByLabel('Draft JSON')
        .fill(JSON.stringify({ name: 'Shipment', fields: [{ name: 'a' }] }));
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      const notice = page.getByText('Your model is saved, and unlisted');
      await expect(notice).toBeVisible();
      const link = await page.getByLabel('Link to My models').inputValue();
      expect(link).toMatch(/\/mine\/c-MockCollection\d+$/);
      await shotOf(page.locator('.access-banner').first(), 'w21-my-models-notice', theme);
      // the same link is kept, and a second save (in the app: a reload would reset the mock) joins it with no new notice
      const kept = await page.evaluate(() => localStorage.getItem('plume-collection'));
      expect(link.endsWith(`/mine/${kept}`)).toBe(true);
      await page.getByRole('link', { name: 'Models', exact: true }).first().click();
      const mine = page.getByRole('region', { name: 'Your models' });
      await expect(mine.getByRole('link', { name: 'Shipment' })).toBeVisible();
      await suggestions(page);
      await page.getByRole('button', { name: 'Generate Customer', exact: true }).click();
      panel = page.getByRole('region', { name: 'Generation session' });
      await panel
        .getByLabel('Draft JSON')
        .fill(JSON.stringify({ name: 'Customer', fields: [{ name: 'a' }] }));
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Customer' })).toBeVisible();
      await expect(page.getByText('Your model is saved, and unlisted')).toHaveCount(0);
      expect(await page.evaluate(() => localStorage.getItem('plume-collection'))).toBe(kept);
    });
  });
}

test('on a narrow screen the My models page does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await hold(page, DEMO_COLLECTION);
  await page.goto(`/mine/${DEMO_COLLECTION}`);
  await expect(page.getByRole('region', { name: 'Models' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
