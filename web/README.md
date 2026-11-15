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
PLUME_E2E_API_URL=http://127.0.0.1:18480 npm run e2e:real:docker   # specs in e2e-real/, dev server without mocks
```

Every page is checked with axe in light and dark: no serious or critical violations (contrast included).

## Notes

- The maintainer key is typed at sign-in and held in memory only (`src/app/authStore.ts`); a reload signs out.
- Fonts are self-hosted (`@fontsource-variable/*`); there is no third-party request.
- `src/api/types.ts` is hand-written until the backend publishes its OpenAPI document (P3).
