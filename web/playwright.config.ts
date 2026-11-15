import { defineConfig, devices } from '@playwright/test';

const PORT = 18473;

/**
 * Two modes:
 *  - default: ./e2e against the Vite dev server with MSW mocks (VITE_USE_MOCKS=true);
 *  - PLUME_E2E_API_URL=http://127.0.0.1:18480: ./e2e-real against the real API of the compose stack
 *    (`make up`, then load the fixture packages: shopify-mini, test-catalog, second-catalog). The dev server
 *    is started without mocks and points at that API.
 * PLUME_E2E_BASE_URL runs either set against an already running web server (no dev server is started).
 * Use the same Docker image in CI as locally: mcr.microsoft.com/playwright:v1.62.1-noble (see `npm run e2e:docker`).
 */
const external = process.env.PLUME_E2E_BASE_URL;
const realApi = process.env.PLUME_E2E_API_URL;

export default defineConfig({
  testDir: realApi ? './e2e-real' : './e2e',
  outputDir: process.env.PLUME_E2E_OUTPUT_DIR ?? '/tmp/plume-web-e2e-results',
  // the first page load of a run compiles the app on a cold dev server; give assertions room
  expect: { timeout: 10_000 },
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
        env: realApi
          ? { VITE_API_BASE_URL: realApi, VITE_USE_MOCKS: 'false' }
          : { VITE_API_BASE_URL: 'http://127.0.0.1:18480', VITE_USE_MOCKS: 'true' },
      },
});
