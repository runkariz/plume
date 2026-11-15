import { defineConfig, devices } from '@playwright/test';

const PORT = 18473;

/**
 * Runs against the Vite dev server with MSW mocks (VITE_USE_MOCKS=true) until the compose stack exists.
 * Pass PLUME_E2E_BASE_URL to run against an already running stack instead (no dev server is started).
 * Use the same Docker image in CI as locally: mcr.microsoft.com/playwright:v1.62.1-noble (see `npm run e2e:docker`).
 */
const external = process.env.PLUME_E2E_BASE_URL;

export default defineConfig({
  testDir: './e2e',
  outputDir: process.env.PLUME_E2E_OUTPUT_DIR ?? '/tmp/plume-web-e2e-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: external ?? `http://127.0.0.1:${PORT}`,
    viewport: { width: 1080, height: 800 },
    launchOptions: process.env.PLUME_CHROMIUM_PATH
      ? { executablePath: process.env.PLUME_CHROMIUM_PATH }
      : {},
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1080, height: 800 } },
    },
  ],
  webServer: external
    ? undefined
    : {
        command: 'npm run dev',
        url: `http://127.0.0.1:${PORT}`,
        reuseExistingServer: !process.env.CI,
        env: { VITE_API_BASE_URL: 'http://127.0.0.1:18480', VITE_USE_MOCKS: 'true' },
      },
});
