# Plume web

The web UI of Plume: browse API knowledge bases, try search / ask / check-call, run the maintainer wizard
(upload, review, live build, publish) and create canonical models across APIs.

React 19 + TypeScript (strict) + Vite, React Router, React Flow (the mapping view), Vitest + Testing Library,
Playwright + axe. It talks **only** to the Plume HTTP API; it has no server of its own.

## Quick start

You need Node 24 and npm. From this folder:

```bash
cp .env.example .env.local     # VITE_API_BASE_URL is required; VITE_USE_MOCKS=true serves sample data
npm ci
npm run dev                    # http://127.0.0.1:18473
```

With `VITE_USE_MOCKS=true` (the default in `.env.example`) the app runs on built-in sample data (MSW), so you
can work on the UI without a backend. To use the real API, start the stack from the repo root (`make up`, API on
`http://127.0.0.1:18480`), load a package (`plume load tests/fixtures/packages/shopify-mini`), and set
`VITE_USE_MOCKS=false` in `.env.local`.

Maintainer pages need a token: the server only starts with tokens of at least 16 characters, for example
`PLUME_MAINTAINER_TOKENS='["pl_dev_local_web_e2e"]' make up`. Type that token at **Maintainer** → sign in.

## Checks (all must pass before a merge)

```bash
npm run lint          # ESLint, 0 warnings (includes jsx-a11y)
npm run typecheck     # tsc, strict
npm test              # Vitest + Testing Library (a render test per page: loading, empty, error)
npm run build         # tsc + vite build
npm run format:check  # Prettier (npm run format fixes it)
```

## End-to-end tests (Playwright + axe)

The browser comes from a pinned Docker image so everybody (and CI) runs the same one; do not install browsers on
the host. `@playwright/test` is pinned to the same version (1.62.1).

```bash
npm run e2e:docker             # ./e2e against the dev server with mocks; every page in light and dark, axe included
```

Against the real API (specs in `e2e-real/`; they publish and create models, so they run one at a time):

```bash
# 1. from the repo root: a stack with a maintainer token (fixtures must be loaded; see above)
PLUME_MAINTAINER_TOKENS='["pl_dev_local_web_e2e"]' make up
# 2. here:
PLUME_E2E_API_URL=http://127.0.0.1:18480 PLUME_E2E_TOKEN=pl_dev_local_web_e2e npm run e2e:real:docker
```

The models spec (`e2e-real/models.spec.ts`) creates models and needs a **fresh stack** (`down -v`, up, load the
fixtures): once an Order model exists for the current builds, Generate answers "ready" and skips the generation
flows. Without a model key on the server, server-side generation answers 503 (the spec checks that state).

Useful variables: `PLUME_E2E_SHOTS_DIR` (a folder **outside the repo**, mounted into the container, receives
light/dark screenshots), `PLUME_E2E_BASE_URL` (use an already running web server), `PLUME_E2E_OUTPUT_DIR`.
The docker scripts mount the whole repo (`/repo`) because some specs read `tests/fixtures`.

axe fails a test on any serious or critical violation (colour contrast included), in both themes. If you add a
colour, check it with `src/lib/color.ts` (WCAG ratios) or just run the e2e suite.

## How the code is organised

```
src/
  api/          typed fetch client (client.ts), types, SSE parser (sse.ts), env config (config.ts)
  app/          layout, routes, theme, in-memory maintainer key (authStore.ts)
  components/   the small kit: Button, Card, Chip, Field, Banner, Stepper, Segmented, Crumbs, states...
  pages/        Home, ApiDetailPage, TryItPage; maintainer/ (wizard); models/ (picker, suggestions, mapping view)
  mocks/        MSW handlers + sample data from the design mockups (used by dev, unit tests and ./e2e)
  styles/       tokens.css (colours, light + dark), kit.css (components), layout.css (pages)
  lib/          formatting, colour helpers, small pure functions
e2e/            Playwright specs against the mocks
e2e-real/       Playwright specs against the real API
```

Where to change what:

- **A new API field or route**: `docs/openapi.json` (repo root) is the truth. Update `src/api/types.ts` and
  `src/api/client.ts` by hand, then the mock in `src/mocks/handlers.ts` and its sample data, so mock runs and the
  real API stay in step. Run the real e2e to confirm.
- **A new page**: add it in `src/pages`, register it in `src/app/routes.tsx`, give it a render test with loading,
  empty and error states, and add it to an e2e spec so axe covers it.
- **Colours and spacing**: tokens in `src/styles/tokens.css` (light values, a dark set, and the `data-theme`
  override). Do not hard-code colours in components.

## Rules this app follows

- **No hard-coded API URL.** `VITE_API_BASE_URL` is required (`src/api/config.ts` throws without it).
- **No secrets in the app.** The maintainer token is typed at sign-in and kept in memory only
  (`src/app/authStore.ts`): a reload signs out on purpose. Never put it in local or session storage. E2E specs
  therefore navigate inside the app after signing in (a `page.goto` reload would sign out).
  The one thing kept in `localStorage` is the list of **owner keys** (`plume-owner-keys`, `src/lib/ownerKeys.ts`): the
  server hands one out once when someone without a token creates a model, and it only lists "Your models" (it
  cannot change or release anything; a model's link works without it).
- **No third-party requests.** Fonts are self-hosted (`@fontsource-variable/*`); an API's icon is loaded only
  from a relative `/v1/...` path on the API (`src/lib/icon.ts`), never from an external URL, with the letter logo
  as the fallback. Do not add analytics or CDNs.
- **All server text is untrusted.** Quotes, snippets, file names and model text render as plain text; the only
  markup allowed is `**bold**` in open questions (`src/lib/richText.tsx`).
- **Who sees which model.** Released models are **Official** and the only ones in public lists; unlisted models
  (made without a token) open by their link; unreleased ones need a maintainer. The web never decides this: it shows
  what the API returns (`visibility`) and says so. A failed lazy chunk after a deploy reloads once, then shows
  the error page (`src/app/chunkReload.ts`, `RouteError.tsx`).
- **Brand marks.** The header uses the owner's dark mark (light theme) and white mark (dark theme), small 96 px
  variants of the original 1024 px files in `public/` (favicon, apple-touch icon and the web manifest too). To
  change them, put new originals in, regenerate the small sizes (downscale in steps, see git history of
  `public/`) and keep the file names.
- **The model graph** (`ModelWorkbench`): the control box over the left of the canvas (filter by name, API
  checkboxes, mapping list) and the detail panel beside it. The filter, the checked APIs, the view and the selected
  mapping are in the URL (`f`, `show`, `view`, `scope`, `field`, `api`). Unchecked APIs and filtered-out mappings
  are greyed out, never hidden. It takes the model and the state as props, so another page or an embedded view can
  reuse it.
- **Honest numbers.** Quality scores are shown only when the server sends them ("Not evaluated" otherwise);
  never invent a value to fill a mockup.
- **Accessibility.** Inputs have labels, focus is visible, the graph has a keyboard alternative (the Mapping
  list), and both themes pass axe. Small screens: nothing scrolls sideways at 375 px.

## Troubleshooting

- _The page is blank / "VITE_API_BASE_URL is not set"_: create `.env.local` from `.env.example`.
- _Port 18473 is busy_: the dev server uses a fixed port on purpose (`strictPort`); stop the other process.
- _CORS errors against the real API_: the API allows `http://127.0.0.1:18473` and `http://localhost:18473`; open
  the app on one of those, not on another host name.
- _Maintainer calls answer 401/503_: the stack needs `PLUME_MAINTAINER_TOKENS` (16+ characters) and you must sign
  in with one of them.
- _E2E fails on the very first page after a clean checkout_: the first run compiles the app on a cold dev server;
  run it again (assertions already wait up to 10 s).
- _npm audit warnings_: they are for dev dependencies; the app ships only the built bundle.
