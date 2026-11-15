import { expect, type Page } from '@playwright/test';
import { expectNoSeriousA11y, settle, shot, test, THEMES } from './helpers';

/** Related concepts and creating a set: with Claude (a session) and, signed in, on the server (a job). */
const RELATED = '/models/related?apis=shopify,woocommerce&concept=Product';
const TOKEN = 'pl_e2e_token_value';

async function signIn(page: Page) {
  await page.goto('/maintainer');
  await page.getByLabel('Email').fill('maintainer@example.com');
  await page.getByLabel('Access token').fill(TOKEN);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Maintainer', exact: true })).toBeVisible();
}

const bar = (page: Page) => page.getByRole('region', { name: 'Create a model set' });

for (const theme of THEMES) {
  test.describe(`related concepts (${theme})`, () => {
    test.use({ theme, viewport: { width: 1280, height: 900 } });

    test('related concepts with their evidence, and the alias to accept', async ({ page }) => {
      await page.goto(RELATED);
      await expect(bar(page)).toBeVisible();
      await expect(
        page.getByRole('heading', { name: 'Concepts related to Product', level: 1 }),
      ).toBeVisible();
      await expect(
        page.getByRole('list', { name: 'Related concepts' }).getByRole('checkbox'),
      ).toHaveCount(4);
      // the API chips under the title sit in one row
      const chips = page.getByRole('list', { name: 'Selected APIs' }).getByRole('listitem');
      const [c1, c2] = [await chips.nth(0).boundingBox(), await chips.nth(1).boundingBox()];
      expect(Math.abs((c1?.y ?? 0) - (c2?.y ?? 99))).toBeLessThan(4);
      await page.getByText('Evidence in the docs (3)').click(); // Variant: nested, sub-resource, id field
      await expect(
        page
          .getByRole('list', { name: 'Related concepts' })
          .getByText('GET /admin/api/{version}/products/{product_id}/variants.json'),
      ).toBeVisible();
      const alias = page.getByRole('region', { name: 'Same thing, different names?' });
      await expect(alias).toContainText('The docs do not say they are the same thing');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w17-related', theme);
    });

    test('pick concepts, accept the alias, create the set with Claude, and the set opens when Claude stores it', async ({
      page,
    }) => {
      await page.goto(RELATED);
      await expect(bar(page)).toBeVisible();
      await page
        .getByRole('checkbox', { name: 'Treat Variant and Variation as one concept' })
        .click();
      await page.getByRole('checkbox', { name: 'Variant', exact: true }).click();
      await page.getByRole('checkbox', { name: 'Image', exact: true }).click();
      await expect(bar(page)).toContainText('3 models: Product, Variant, Image');
      await bar(page).getByRole('button', { name: 'Create with Claude' }).click();
      const panel = page.getByRole('region', { name: 'Create the set with Claude' });
      await expect(panel).toBeVisible();
      await expect(panel.getByLabel('Prompt for Claude')).toContainText(
        'Treat shopify "Variant" and woocommerce "Variation"',
      );
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w17-set-with-claude', theme);
      // Claude's submit_model_set, as the mock server's stand-in
      const id = /get_set_context\("(ss-mock\d+)"\)/.exec(
        (await panel.getByLabel('Prompt for Claude').textContent()) ?? '',
      )?.[1];
      await page.evaluate(
        (sid) =>
          fetch(
            `${new URL(window.location.href).origin.replace(/:\d+$/, '')}:18480/v1/model-sets/sessions/${sid}/draft`,
            { method: 'POST', body: '{}' },
          ),
        id,
      );
      await expect(page).toHaveURL(/\/model-sets\/u-set-mock/, { timeout: 10_000 });
      await expect(
        page.getByRole('heading', { level: 1, name: /Product \+ Variant \+ Image/ }),
      ).toBeVisible();
      await expect(page.getByText('Unlisted: anyone with the link').first()).toBeVisible();
    });

    test('paste a draft yourself: a refused one shows its issues, a member model is stored, then the set opens', async ({
      page,
    }) => {
      await page.goto(RELATED);
      await expect(bar(page)).toBeVisible();
      await page.getByRole('checkbox', { name: 'Image', exact: true }).click();
      await bar(page).getByRole('button', { name: 'Create with Claude' }).click();
      const panel = page.getByRole('region', { name: 'Create the set with Claude' });
      await expect(panel).toBeVisible();
      const box = panel.getByLabel('Draft JSON');
      // a refused set draft: the issues, nothing stored
      await box.fill('{"refuse":"relation"}');
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(panel.getByRole('alert')).toContainText('RELATION_INVALID');
      await settle(page);
      await expectNoSeriousA11y(page);
      await shot(page, 'w17-set-paste-refused', theme);
      // a member's model first
      await panel.getByLabel('This draft is').selectOption('Image');
      await box.fill('{"name":"Image","fields":[{"name":"url"}]}');
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(panel.getByRole('list', { name: 'Stored member models' })).toContainText(
        'Image',
      );
      // then the set that names it
      await box.fill(
        '{"name":"Product + Image","members":{"Product":"u-1","Image":"u-2"},"relations":[]}',
      );
      await panel.getByRole('button', { name: 'Submit draft' }).click();
      await expect(page).toHaveURL(/\/model-sets\/u-set-mock/);
      await expect(page.getByText('Your model set is saved, and unlisted')).toBeVisible();
    });

    test('a maintainer generates the set on the server and lands on the unreleased set to decide', async ({
      page,
    }) => {
      await signIn(page);
      await page.goto(RELATED);
      await expect(bar(page)).toBeVisible();
      // Product + Variant: the server proposes their relation, which is left to decide
      await page.getByRole('checkbox', { name: 'Variant', exact: true }).click();
      await bar(page).getByRole('button', { name: 'Generate the set' }).click();
      await expect(
        page.getByRole('region', { name: 'Generation of the set on the server' }),
      ).toBeVisible();
      await settle(page);
      await shot(page, 'w17-set-generating', theme);
      await expect(page).toHaveURL(/\/model-sets\/set_job/, { timeout: 15_000 });
      await expect(page.getByText('Unreleased: waiting for your review')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Release' })).toBeDisabled();
      await shot(page, 'w17-set-generated', theme);
    });

    test('a suggestion and a model link to their related concepts', async ({ page }) => {
      await page.goto('/models/suggest?apis=shopify,woocommerce,mirakl');
      await page.getByRole('link', { name: 'Related concepts of Order' }).click();
      await expect(page).toHaveURL(
        /\/models\/related\?apis=shopify,woocommerce,mirakl&concept=Order/,
      );
      await expect(
        page.getByRole('heading', { name: 'Concepts related to Order', level: 1 }),
      ).toBeVisible();
    });
  });
}

test('on a narrow screen nothing scrolls sideways and the create bar stays reachable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(RELATED);
  await expect(bar(page)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.getByRole('checkbox', { name: 'Image', exact: true }).click();
  await expect(bar(page).getByRole('button', { name: 'Create with Claude' })).toBeInViewport();
});
