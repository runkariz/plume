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

Against a build served on one origin (nginx proxying `/v1`, see Deploying), set `PLUME_E2E_BASE_URL` to the web's
address, `PLUME_E2E_API_URL` to the API (the specs also call it directly) and `PLUME_E2E_SAME_ORIGIN=true`, so the
specs expect relative `/v1/...` calls and icon paths.

`e2e-real/zz-warnings.spec.ts` needs a test-catalog that has a POST `/api/{version}/orders`, which the default fixtures
lack: copy `tests/fixtures/packages/test-catalog`, copy its `connector/endpoints/get-api-v1-orders` to
`post-api-v1-orders`, set `"method": "POST"` (and drop `endpointId`) in that `request.json`, load the copy, and run the
spec with `PLUME_E2E_WRITE_ONLY=true`; it is skipped otherwise.

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

- **No hard-coded API URL.** `VITE_API_BASE_URL` is required (`src/api/config.ts` throws without it). An absolute
  URL is for dev; an EMPTY value (or `/`) means the web and the API share an origin and every call is a relative
  `/v1/...` request: the recommended deploy (see Deploying below).
- **The maintainer token is not stored for good.** It is typed at sign-in and kept in memory and in
  `sessionStorage` (`src/app/authStore.ts`): a refresh keeps the session, closing the tab, Sign out or a 401 from
  the API ends it. Never put it in the URL, `localStorage` or a log. Blocked storage falls back to memory. See
  docs/security.md (Web UI session) for the trade-off and the cookie follow-up. The one other thing kept in
  `localStorage` is the id of the person's **My models link** (`plume-collection`, `src/lib/collection.ts`): no
  accounts, the link is the identity. A save without a token (paste, Create with Claude, an anonymous edit) sends it
  as `?collection=`, and the server answers `collection: {id, url, created, note?}` (a new link on the first save, or when the one
  sent is unknown: then the note says so); the id is kept, and the link is shown once on arrival (`CollectionNotice`).
  It is a list, not a key: it only shows which models and sets are under it. `/models` "Your models" is that link's
  content (models and sets) with the link to copy; "Open another My models link" takes a link or its id and checks
  it first; `/mine/<id>` (`src/pages/mine/`) is the page of any link, with "Use this link in this browser" and "Merge
  my other link into this one" (`POST /v1/collections/{id}/merge`), and points to where a merged link's models went.
  A link lists the version saved INTO it: when someone with the model's link saved a newer one (it goes to their own
  link), the item says "A newer version exists (vN)" and links to it (`newerVersion`).
  Old owner keys (`plume-owner-keys`, `src/lib/ownerKeys.ts`) are read once, on /models: `POST /v1/models/mine`
  answers `collections`, the first link is kept (the others are merged into it) and the keys are forgotten.
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

## Model sets (several models and the relations between them)

`/model-sets/:id` (`src/pages/sets/`): the top level is a database-like diagram of the models (boxes with their field
counts and coverage per API) and their relations (arrows labelled with cardinality and kind; dashed = a proposal not
decided yet). It uses the same control box as the mapping graph (`ControlBox`: filter, API checkboxes that grey out,
a keyboard list), the state in the URL (`f`, `show`, `sel`), and the detail panel beside it. A model opens its field
mapping (`/models/:modelId`); a relation shows how each API documents it and the designs it could have.

The editor stages the chosen design per relation (the options come from the server's `editableOptions`; a design that
is not possible yet is disabled with the server's reason) and saves them with ONE `POST /v1/model-sets/{id}/relations`,
which makes a NEW version (409: not the latest version; 422: the design was refused). Release is blocked while
relations are undecided and lists the models released with the set. See `src/api/types.ts` for the shapes.

### Related concepts and creating a set

`/models/related?apis=a,b&concept=Product` (`src/pages/sets/RelatedConcepts.tsx`) is reached from a suggestion or a
model ("Related concepts"). It calls `POST /v1/models/suggest-related` (deterministic, no LLM) and lists what the docs
connect to the concept (Variant, Image, ...), per API how (nested objects, sub-resource, id field, model reference),
the designs the evidence supports, and the quotes. Names that differ between the APIs (variant / variation) come as an
**alias offer**: nothing is merged unless the person ticks "Treat ... as one concept"; the first chosen API's name then
stands for it and the request carries `aliases: [{concept, names: {apiId: name}}]`.

The person picks 1..7 related concepts (a set has 2..8 models) and creates the set:

- **With Claude** (anyone): `POST /v1/model-sets/sessions`, the page shows the server's `claudePrompt` and polls
  `GET /v1/model-sets/sessions/{id}` (snake_case `set_id`); it opens `/model-sets/{id}` when Claude has stored the set
  (unlisted without a token, unreleased with one).
- **On the server** (a signed-in maintainer, unless `generation` is false): `POST /v1/model-sets/generate`, a job on
  `/v1/models/jobs/{id}/events` (`member`, `proposals`, `accepted`/`done` with `setId`). The set opens unreleased with
  every proposed relation undecided. A server without a model key answers 503: the page offers the Claude path.

## The model view as an MCP App (the widget)

Claude web and Desktop show a canonical model inline through an MCP App: one self-contained HTML file that Plume
serves as `ui://plume/model-view` (see `docs/mcp-apps.md`). It is the same React mapping view (`ModelWorkbench`:
graph, control box, detail panel) built as a second entry.

```bash
npm run build:widget     # builds web/dist-widget/widget.html, checks it, copies it to
                         # ../src/plume/interfaces/mcp/apps/model-view.html (commit that file)
```

How it works (`src/widget/`): `protocol.ts` is the host side of the spec (JSON-RPC over `postMessage`:
`ui/initialize`, `initialized`, `tool-result`, `host-context-changed`, `size-changed`, `ui/open-link`);
`model.ts` reads the model from `structuredContent.model ?? structuredContent` (and shows a refused draft);
`WidgetApp.tsx` is the view; it follows the host's theme and reports its height.
A **model set** result (`structuredContent.kind === "model_set"`, or `{set}` from submit/release) renders `SetPanel`:
the same `SetWorkbench` as the web page (diagram, control box, detail), read only (no design choices; "Open in
Plume" is the way on), plus the models and relations as text and the open questions. `SetDetail` takes its links as
render props, so the bundle contains no router.

A save without a token (submit_model_draft / submit_model_set) carries the person's **My models link** in
`structuredContent.collection` (`{id, url, created, note?}`; the tool text says "Your models: <url>"): the widget
shows it (`CollectionNotice`: "Your models: <link>", Copy with a fallback for a sandbox that refuses the clipboard,
"Open My models" through the host when the link is absolute, the server's note, Dismiss), as text only: no storage,
no request. A maintainer save has `collection: null` and shows nothing.

Rules it must keep (the host's default CSP is `default-src 'none'`, scripts and styles inline, images `data:`,
`connect-src 'none'`, and the frame has no storage):

- everything inline in the one file, no remote URL, **no font files** (the CSP has no `font-src`, so even a
  `data:` font is blocked: the view uses the host's `--font-sans` or the system fonts);
- no `fetch`, no storage, no router; package text only as React text nodes; icon URLs are dropped (letter tiles);
- a fixed canvas height (the host sizes the frame from the content, so `vh` would loop).
- the build ignores `.env` files and `VITE_*` shell variables (`envDir: false`), so the committed file is the same
  on every machine; the check in `scripts/finish-widget.mjs` fails on any `VITE_` name or local address.

`scripts/finish-widget.mjs` fails the build if the file refers to anything outside itself. `e2e/widget.spec.ts`
runs the BUILT file in a sandboxed iframe under that CSP with the network cut, driven by a stand-in host
(`e2e/widget-host.ts`), and checks axe in both themes: run `npm run build:widget` before it.

## Release review (maintainer): after a publish nothing is held

A new build publishes as usual; afterwards the maintainer reviews its release notes (design:
`docs/design/release-notes.md`). Routes (maintainer session): `/maintainer/apis/:api/builds` (the builds, newest first,
with each review state) and `/maintainer/apis/:api/builds/:build/notes` (`src/pages/maintainer/release/`). The review
shows: the state (`pending | kept | rolled_back`, whether this build is `latest`), "Needs attention" with the server's
one-line reason (never blocking), what changed (confirmed, likely, suspect, no source evidence, breaking), the package
(stream version, rules hash) and gold-score delta, and the **extraction report**: the changes the docs did NOT make but
the extractor did, grouped by rule with the server's explanation (the web holds no rule text). Actions: **Keep**,
**Roll back** (confirm + a required reason, at most 500 characters: `latest` moves to the previous build, the build stays
loaded and untagged), **Roll forward** (Keep on a rolled-back build, while `latest` is still its base), **Copy issues**
and **Download issues (.md)** (one server-built text for stream), and **Promote to confirmed** with a quote the SERVER
verifies against the build's source text (422 `QUOTE_NOT_VERIFIED`: the change stays as it was) with **Demote**.
Suspect and unknown changes appear only on these maintainer routes, never on a public page. Entry points show only when
the API's latest build has notes (feature detection: a server without them shows nothing): the maintainer home, and the
publish step after publishing. Quotes, paths and values are text nodes; a source link only for an http(s) address.

## Releasing models: replacing older ones, and warnings

- **Release asks which older official models of the same concept it replaces** (`ReleaseChoice`): the candidates come
  from `GET /v1/models/{id}/supersedable` (any API set; each with its APIs, `stale`, and `covered` = its APIs are all
  inside the new model's). Nothing is ticked for the maintainer; replacing one that covers an API the new model lacks
  says so. `POST /v1/models/{id}/release` then carries `{supersedes: [ids]}` (409 when an id is not a candidate: nothing
  changes). A replaced model has visibility `superseded`: readable by id, "Superseded by <id>" on its page, out of the
  lists; the new one says "Replaced these official models". An official model's page has "Retire older models of this
  concept" for the same choice after the fact (`POST /v1/models/{id}/supersede`). Sets are not part of this yet.
- **Warnings** (`warnings: [{code, field, api, message}]` on a model, `field` = the canonical path): shown on the model
  page ("Check these mappings", grouped by code, each field linked to its mapping), counted in the review banner ("3
  mappings cite only a request body"), as a note under the mapping in the detail, and as text in the widget. Today:
  `WRITE_ONLY_SOURCE`.
- **Server generation progress**: the job stream sends `heartbeat` (`elapsed`, `round`, `of`, `phase`, `concept`) while
  a model call is in flight; the panel shows "Waiting for the model, 2:41 (round 2 of 3)" and a clock that keeps going
  between heartbeats. A `warnings` event marks a round whose draft was sent back once for repair.

## Deploying: one origin (recommended)

Serve the built `dist/` and the API from the same origin: a reverse proxy sends `/v1/` to the Plume API and
everything else to the app. The browser then makes only same-origin requests, so there is no CORS to configure and
nothing for a browser to block (an embedded browser such as Claude Desktop's refuses cross-origin calls to another
port: `net::ERR_BLOCKED_BY_CLIENT`, "Could not load APIs: Failed to fetch").

```bash
VITE_API_BASE_URL= VITE_USE_MOCKS=false npm run build    # an EMPTY base URL: relative /v1 calls
```

An nginx server block (`proxy_buffering off` is required: the live build and the generation jobs are server-sent
events, which nginx would otherwise hold back until the stream ends):

```nginx
server {
  listen 18493;
  root /srv/plume-web/dist;

  location /v1/ {
    proxy_pass http://127.0.0.1:18490;   # the Plume API
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
    proxy_buffering off;                 # server-sent events
    proxy_read_timeout 1h;               # a stream can stay quiet for a long time
    client_max_body_size 64m;            # package uploads
  }

  location / {
    try_files $uri /index.html;          # single-page app: any path serves index.html
  }
}
```

This is the setup the real e2e suite was run against (nginx in Docker, `PLUME_E2E_SAME_ORIGIN=true`, below). With an
absolute `VITE_API_BASE_URL` instead (dev), the API must allow the web's origin in its CORS list.

## Troubleshooting

- _The page is blank / "VITE_API_BASE_URL is not set"_: create `.env.local` from `.env.example` (an empty value is
  valid: same origin).
- _"Could not load APIs: Failed to fetch" in an embedded browser (`net::ERR_BLOCKED_BY_CLIENT`)_: the web and the API
  are on different origins. Deploy on one origin (above).
- _Port 18473 is busy_: the dev server uses a fixed port on purpose (`strictPort`); stop the other process.
- _CORS errors against the real API_: the API allows `http://127.0.0.1:18473` and `http://localhost:18473`; open
  the app on one of those, not on another host name.
- _Maintainer calls answer 401/503_: the stack needs `PLUME_MAINTAINER_TOKENS` (16+ characters) and you must sign
  in with one of them.
- _E2E fails on the very first page after a clean checkout_: the first run compiles the app on a cold dev server;
  run it again (assertions already wait up to 10 s).
- _npm audit warnings_: they are for dev dependencies; the app ships only the built bundle.
