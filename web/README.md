# Plume web

React + TypeScript (strict) + Vite. Talks only to the Plume HTTP API.

```bash
cp .env.example .env.local     # VITE_API_BASE_URL (required), VITE_USE_MOCKS=true serves sample data via MSW
npm ci
npm run dev                    # http://127.0.0.1:18473
npm run lint && npm run typecheck && npm test && npm run build
```

## End-to-end (Playwright + axe)

Same image locally and in CI, so the browser matches the pinned `@playwright/test`:

```bash
npm run e2e:docker             # mcr.microsoft.com/playwright:v1.62.1-noble, dev server + MSW mocks
PLUME_E2E_SHOTS_DIR=/shots ...  # set (and mount) a directory OUTSIDE the repo to keep light/dark screenshots
PLUME_E2E_BASE_URL=http://host:port npm run e2e   # run against a running stack instead (no dev server)
```

Against the real API (compose stack from the repo root: `make up`, then load the fixtures with
`plume load tests/fixtures/packages/<shopify-mini|test-catalog|second-catalog>`):

```bash
# stack with a maintainer token (the wizard spec needs one); gold sets come from tests/fixtures/gold
PLUME_MAINTAINER_TOKENS='["pl_dev_local_web_e2e"]' make up   # tokens must be at least 16 characters
PLUME_E2E_API_URL=http://127.0.0.1:18480 PLUME_E2E_TOKEN=pl_dev_local_web_e2e npm run e2e:real:docker
```

The real-API specs (`e2e-real/`) cover the reader pages and the maintainer wizard end to end (upload a zipped
fixture package, review, build over SSE, download the dump, publish). They run serially because they publish.
The docker scripts mount the whole repo (`/repo`) because the wizard spec zips `tests/fixtures/packages`.
The maintainer key lives in memory only, so these specs navigate inside the app after signing in
(a `page.goto` reload signs out on purpose).

Every page is checked with axe in light and dark: no serious or critical violations (contrast included).

## Notes

- The maintainer key is typed at sign-in and held in memory only (`src/app/authStore.ts`); a reload signs out.
- Fonts are self-hosted (`@fontsource-variable/*`); there is no third-party request.
- `src/api/types.ts` is hand-written until the backend publishes its OpenAPI document (P3).
