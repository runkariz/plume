import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

export type Theme = 'light' | 'dark';
export const THEMES: Theme[] = ['light', 'dark'];

/** Screenshots go OUTSIDE the repo: set PLUME_E2E_SHOTS_DIR to keep them. */
const SHOTS = process.env.PLUME_E2E_SHOTS_DIR;

export const test = base.extend<{ theme: Theme }>({
  theme: ['light', { option: true }],
  page: async ({ page, theme }, use) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((t) => localStorage.setItem('plume-theme', t), theme);
    await use(page);
  },
});

export async function expectNoSeriousA11y(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  const bad = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(
    bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`),
    'serious/critical axe violations',
  ).toEqual([]);
}

export async function shot(page: Page, name: string, theme: Theme) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `${name}-${theme}.png`), fullPage: true });
}

/** Wait for web fonts so screenshots and layout are stable. */
export async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
}
