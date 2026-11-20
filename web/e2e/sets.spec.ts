import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, openControls, settle, shot, shotOf, test, THEMES } from './helpers';

/** Model sets: the diagram, the control box, the relation editor, release, and the lists. */
const OFFICIAL = '/model-sets/set_shop00000000000000000';
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

for (const theme of THEMES) {
  test.describe(`model sets (${theme})`, () => {
    // a desktop screen: the control box is open by default from 1400 px
    test.use({ theme, viewport: { width: 1440, height: 900 } });

    test('the diagram of the official set: models, relations, the control box and a relation beside it', async ({
      page,
    }) => {
      await page.goto(OFFICIAL);
      await expect(page.getByRole('heading', { level: 1, name: 'Shop' })).toBeVisible();
      await expect(page.locator('.react-flow__node-member')).toHaveCount(3);
      const list = page.getByRole('listbox', { name: 'Models and relations' });
      await expect(list.getByRole('option')).toHaveCount(5);
      await list.getByRole('option', { name: /Order → Product/ }).click();
      const detail = page.getByRole('region', { name: 'Selected model or relation' });
      await expect(detail.getByRole('heading', { name: 'Order → Product' })).toBeVisible();
      await expect(page).toHaveURL(/sel=r%3Aorder-items|sel=r:order-items/);
      await expect(detail).toContainText('cited without quote: the description of line_items');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w16-set', theme);
      await shotOf(
        detail.getByRole('list', { name: 'Sources' }),
        'w39-set-relation-noquote',
        theme,
      );
      // a model: its coverage and the way into the field mapping
      await list.getByRole('option', { name: /^Product\s+\d+ fields/ }).click();
      await expect(detail.getByRole('link', { name: 'Open the field mapping' })).toBeVisible();
    });

    test('unchecking an API greys out what only it documents; nothing is removed', async ({
      page,
    }) => {
      await page.goto(OFFICIAL);
      const box = page.getByRole('complementary', { name: 'Diagram controls' });
      await expect(page.locator('.react-flow__edge')).toHaveCount(2);
      await box.getByRole('checkbox', { name: 'Shopify' }).click();
      await expect(page).toHaveURL(/show=woocommerce/);
      await expect(page.locator('.react-flow__edge.dim')).toHaveCount(1); // product-variants: only Shopify
      await expect(page.locator('.react-flow__edge')).toHaveCount(2);
      await expect(box.getByRole('checkbox', { name: 'WooCommerce' })).toBeDisabled(); // the last one stays
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w16-set-api-focus', theme);
    });

    test("the editor: choose a design, save it as a new version (the user's own unlisted copy)", async ({
      page,
    }) => {
      await page.goto(`${OFFICIAL}?sel=r:product-variants`);
      const detail = page.getByRole('region', { name: 'Selected model or relation' });
      await detail.getByRole('radio', { name: /Variant refers to Product/ }).click();
      const bar = page.getByRole('region', { name: 'Changes to save' });
      await expect(bar).toContainText('1 relation changed');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w16-set-editor', theme);
      await bar.getByRole('button', { name: 'Save as a new version' }).click();
      await expect(page.getByText('Saved as a new version')).toBeVisible();
      await expect(page.getByText('Your model set is saved, and unlisted')).toBeVisible();
      await expect(page).toHaveURL(/\/model-sets\/u-set/);
    });

    test('a maintainer cannot release while a relation is undecided; deciding it unblocks the release', async ({
      page,
    }) => {
      await signIn(page);
      await page.getByRole('link', { name: 'Models', exact: true }).click();
      await page
        .getByRole('region', { name: 'Sets waiting for review' })
        .getByRole('link', { name: 'Catalog (draft)' })
        .click();
      await expect(page.getByText('Unreleased: waiting for your review')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Release' })).toBeDisabled();
      await expect(
        page.getByText(/Release is blocked: 1 relation is not decided yet/),
      ).toBeVisible();
      await page.getByRole('button', { name: 'Order → Product' }).click();
      await expect(page.getByText('Proposal: to decide')).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w16-set-undecided', theme);
      await page
        .getByRole('region', { name: 'Selected model or relation' })
        .getByRole('radio')
        .first()
        .click();
      await page.getByRole('button', { name: 'Save as a new version' }).click();
      await expect(page.getByText('Saved as a new version')).toBeVisible();
      await page.getByRole('button', { name: 'Release' }).click();
      await expect(page.getByText('Released: the set is Official')).toBeVisible();
      await expect(page.getByText('These models were released with it:')).toBeVisible();
      await shot(page, 'w16-set-released', theme);
    });

    test('the Models page lists the official sets', async ({ page }) => {
      await page.goto('/models');
      const official = page.getByRole('region', { name: 'Official model sets' });
      await expect(official.getByRole('link', { name: 'Shop' })).toBeVisible();
      await settle(page);
      await expectNoSeriousA11y(page);
    });
  });
}

test('on a narrow screen the control box starts closed and the detail stacks under the diagram', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(OFFICIAL);
  const toggle = page.getByRole('button', { name: /Filter models and relations/ });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await openControls(page, /Filter models and relations/);
  const g = await page.getByRole('group', { name: /Model set diagram/ }).boundingBox();
  const d = await page.getByRole('region', { name: 'Selected model or relation' }).boundingBox();
  expect((d?.y ?? 0) + 1).toBeGreaterThanOrEqual((g?.y ?? 0) + (g?.height ?? 0));
});
