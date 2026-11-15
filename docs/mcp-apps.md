# The model view as an MCP App

When Claude returns a canonical model, hosts that support **MCP Apps** (Claude web and Desktop)
show Plume's mapping view inline. Hosts that don't (Claude Code) show the text result, which
has a summary and the share link.

## What the spec says (checked 2026-11-16)

Sources:
- The installed Python SDK, `mcp` 2.3.0, `mcp/server/apps.py` (in-core MCP Apps support). This
  is the primary source for the wire format Plume emits.
- The ext-apps repository, https://github.com/modelcontextprotocol/ext-apps. SEP-1865, "MCP Apps:
  Interactive User Interfaces for MCP". Specification `specification/2026-01-26/apps.mdx` is
  **Stable (2026-01-26)**; `specification/draft/apps.mdx` is **Draft**. The README lists the same
  two versions.
- https://modelcontextprotocol.io/specification/draft/extensions/apps, which the SDK docstring
  cites, returned 404 on 2026-11-16.

Points read verbatim are marked **verified**. Points taken from a summary of the spec page are
marked **summary**; they are consistent with the SDK but were not read word for word.

| Topic | What it says | |
|---|---|---|
| Extension id | `io.modelcontextprotocol/ui`. Negotiated through the capability extensions: the server advertises `capabilities.extensions["io.modelcontextprotocol/ui"]`, and a client that supports it lists `mimeTypes: ["text/html;profile=mcp-app"]` | verified (SDK); client side: summary + SDK `client_supports_apps` |
| Resource | URI scheme `ui://`, MIME type **`text/html;profile=mcp-app`** ("MUST be"). Hosts don't render a `ui://` resource under any other type | verified (spec + SDK) |
| Tool → view | Tool `_meta.ui.resourceUri = "ui://…"`. The flat `_meta["ui/resourceUri"]` is deprecated and "will be removed before GA" | verified |
| Tool visibility | `_meta.ui.visibility`, default `["model", "app"]`. Hosts MUST NOT list tools without `"model"` to the agent, and MUST reject `tools/call` from an app for tools without `"app"`. Cross-server app calls are blocked | verified |
| Resource `_meta.ui` | `csp {connectDomains, resourceDomains, frameDomains, baseUriDomains}`, `permissions {camera, microphone, geolocation, clipboardWrite}`, `domain`, `prefersBorder`. Allowed on `resources/list` and on `resources/read` contents | verified |
| Default CSP (no `csp` declared) | Host MUST use `default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' data:; object-src 'none'; connect-src 'none'`. Inline script and style work; nothing remote loads; no fetch | verified (draft list; 2026-01-26 differs only by `object-src`) |
| Transport host ↔ view | JSON-RPC 2.0 over `postMessage` | verified |
| Handshake | The view sends request `ui/initialize` `{protocolVersion, appInfo, appCapabilities}`. The host answers `{protocolVersion, hostCapabilities, hostInfo, hostContext}`. The view then sends `ui/notifications/initialized`. The host sends nothing before that | verified |
| Tool data to the view | `ui/notifications/tool-input` (the arguments, once). `ui/notifications/tool-result` carries a standard `CallToolResult`: `content` is for the model and text-only hosts; `structuredContent` is for the UI and is not added to the model context | summary |
| Size | The view sends `ui/notifications/size-changed {width?, height?}` | verified |
| Theming | `hostContext.theme` ("light" or "dark"), `hostContext.styles.variables` (CSS variables such as `--color-background-primary`, `--color-text-primary`, `--font-sans`, which may be a subset), `styles.css.fonts`, `displayMode`, `containerDimensions`, `locale`, `timeZone`, `platform`. Changes arrive as `ui/notifications/host-context-changed` (partial; merge) | verified (fields); summary (change payload) |
| Calls from the view | `tools/call` through the host, which needs the host's `serverTools` capability, plus `resources/read`. Also `ui/open-link` (host capability `openLinks`) and `ui/message` (`message`) | verified (`tools/call`); summary (`open-link`, `message`) |
| Without support | "If host does not support MCP Apps, tool behaves as standard tool (text-only fallback)". Tools must return meaningful `content` | verified (first part) |
| Reference host | `examples/basic-host` in ext-apps: `npm install && npm run start`, http://localhost:8080, servers from `SERVERS='["http://…/mcp"]'`, default `http://localhost:3001/mcp`. Whether it speaks Streamable HTTP isn't stated. It needs a `git clone` and `npm install` from the internet | verified (README) |

## What Plume does

- **Resource** `ui://plume/model-view` (`text/html;profile=mcp-app`, `prefersBorder: true`, no
  `csp`) on **both** the reader MCP (`/mcp`) and the maintainer MCP (`/maintainer/mcp`),
  registered through the SDK's `Apps` extension. That also advertises
  `io.modelcontextprotocol/ui` in the server capabilities.
- **Bundle**: one self-contained HTML file, `src/plume/interfaces/mcp/apps/model-view.html`,
  packaged with Plume and in the image. `PLUME_MCP_APP_HTML=<file>` serves another file. Today
  it's a placeholder: a vanilla script doing the handshake and a plain table rendered with
  `textContent`. The web app's mapping view, built as one inlined file, replaces it.
- **Tools with the view** (`_meta.ui.resourceUri`):

  | Tool | Server |
  |---|---|
  | `get_model` | reader + maintainer |
  | `submit_model_draft` | reader + maintainer |
  | `release_model` | maintainer |
  | `discard_model` | maintainer |
  | `get_generation` (carries `model` once it succeeds) | maintainer |

  `revise_model` returns a working session, not a model, so it has no view.
- **Write tools are model-only** (`_meta.ui.visibility = ["model"]`): `start_model_session`,
  `submit_model_draft`, `revise_model`, `release_model`, `discard_model`, `generate_model`,
  `publish_build`. The view can only call read tools (`get_model`, `get_document`, `find_fact`,
  `search_docs`, …).
- **Result shape**:
  - `structuredContent` is unchanged from before:
    - `get_model`, `release_model` and `discard_model`: the model JSON itself.
    - `submit_model_draft`: `{accepted, snapshot_id, visibility, version, share_url, model, …}`.
    - `get_generation`: the job, plus `model` once it succeeded.
    - So the view reads `structuredContent.model ?? structuredContent`.
  - The model JSON carries `lineage`, `visibility`, `official`, `shareUrl` / `sharePath`, and
    `inputs[].logo.url`.
- **Text content (the fallback)** is complete without the view:
  - **Summary**: name, id, visibility, version, APIs, coverage per API, open questions and
    citations checked.
  - **Link**: `shareUrl` when `PLUME_WEB_PUBLIC_URL` is set, else `sharePath`.
  - **`submit_model_draft`** also returns the `owner_key` with the instruction to save it, or
    the refusal issues.
  - **`get_model`** also returns the full model JSON, because a host that renders the view
    doesn't give `structuredContent` to the model.

## Rules for the bundle (plume-9a)

- One HTML file with everything inlined. Load nothing remote: the host default CSP blocks it
  anyway. No `fetch`/XHR: data arrives only through `ui/notifications/tool-result` and
  `tools/call`.
- Render every package or evidence string as text (React text nodes; no
  `dangerouslySetInnerHTML`, no `innerHTML`).
- Follow the handshake above. Apply `hostContext.theme` and `styles.variables`, and listen for
  `host-context-changed`. Report the height with `size-changed`.
- Clicking a node may call read-only reader tools through `tools/call` (`get_document`,
  `find_fact`). Hosts refuse write tools, which are model-only.
- "Open in Plume": `ui/open-link` with `shareUrl`, only when the host offers `openLinks`;
  otherwise show the link as text.

## How to test locally

### The reference host (ext-apps `basic-host`)

Tested 2026-11-16 with ext-apps **v2.1.0** (commit `ea3e9d0e624a20bc1c51310292f09d9b8ed17161`),
cloned outside the repository. `get_model` rendered the view. The
screenshot is in the session scratchpad, `basic-host-get_model.png`.

1. Get the host. Its `serve.ts` takes `HOST_PORT` / `SANDBOX_PORT`, but `src/implementation.ts`
   hard-codes the sandbox URL `http://localhost:8081/sandbox.html`. Replace that line to use
   your sandbox port (Plume's block is 18400-18499; 8080/8081 are not allowed here). Install it
   on its own rather than as part of the ext-apps workspace (which builds with `bun`):

   ```bash
   git clone https://github.com/modelcontextprotocol/ext-apps.git && cd ext-apps && git checkout v2.1.0
   cp -r examples/basic-host ../basic-host && cd ../basic-host
   sed -i 's|"@modelcontextprotocol/ext-apps": "^2.1.0"|"@modelcontextprotocol/ext-apps": "2.1.0"|' package.json
   # src/implementation.ts: SANDBOX_PROXY_BASE_URL -> http://localhost:18461/sandbox.html
   npm install
   NODE_ENV=development INPUT=index.html npx vite build
   NODE_ENV=development INPUT=sandbox.html npx vite build   # (tsc needs @types/cors; skipped)
   ```

2. Run a Plume stack whose MCP allows the host's browser origin. basic-host's MCP client runs
   **in the browser**, so it needs CORS. Set `PLUME_MCP_CORS_ORIGINS='["http://localhost:18460"]'`
   on the `mcp` service; it's off by default, and real hosts don't need it. Set
   `PLUME_WEB_PUBLIC_URL` for real share links. Then load packages and save a model.
3. `HOST_PORT=18460 SANDBOX_PORT=18461 SERVERS='["http://localhost:<mcp port>/mcp"]' npx tsx serve.ts`,
   open `http://localhost:18460/index.html`, pick server `plume`, tool `get_model`, input
   `{"snapshot_id": "<id>"}`, then **Call Tool**.
   - Headless: this machine lacks Chromium's system libraries. Use
     `mcr.microsoft.com/playwright:v1.62.1-noble` with `--network host`.

### Claude Desktop (local connector through `mcp-remote`)

The owner's path: Claude Desktop starts a stdio bridge to Plume's HTTP MCP (over the port
forward):

```json
{
  "mcpServers": {
    "plume": { "command": "npx", "args": ["-y", "mcp-remote", "http://127.0.0.1:18491/mcp"] }
  }
}
```

What the sources say about local / stdio servers:
- The spec sets no transport condition for MCP Apps. The view is fetched with ordinary
  `resources/read`, and its tool calls are ordinary `tools/call`; the iframe ↔ host leg is
  `postMessage` inside the host.
- The ext-apps testing guide (`docs/testing-mcp-apps.md` at v2.1.0) lists Claude with both
  "Remote MCP servers (over HTTP)" and "Local MCP servers (over stdio)" as MCP Apps hosts. The
  README configures its example App servers in "an MCP client that supports stdio (Claude
  Desktop, VS Code, etc.)".
- Not stated anywhere, and **untested here**: whether `mcp-remote` passes through the Apps
  negotiation (`capabilities.extensions["io.modelcontextprotocol/ui"]` in `initialize`, both
  directions) and `_meta` on tools and resources. If Claude Desktop shows only text for
  `get_model`, check that first. The text fallback (summary + link) still works.
- Claude web (claude.ai) cannot reach `127.0.0.1`. It needs a public HTTPS URL for the MCP; the
  guide suggests a `cloudflared` tunnel. That's the owner's decision; Plume opens none.

## Testing

- Unit (`tests/unit/interfaces/test_mcp_app.py`): the resource is listed and readable with the
  MIME type; the capability is advertised; tools carry `resourceUri` / `visibility`; results
  carry the structured model and a text fallback with the link; the bundle override works; the
  placeholder loads nothing remote and uses `textContent`.
- e2e (`tests/e2e/test_models_stack.py`): the same resource and tool metadata over Streamable
  HTTP from the Docker image.
- Local render (offline, 2026-11-16): a stand-in host checks the handshake end to end. It puts
  the served resource in an `<iframe sandbox="allow-scripts">` with the spec's default CSP
  injected, and runs in the `mcr.microsoft.com/playwright:v1.62.1-noble` container with
  `--network none`. It answers `ui/initialize` with a `hostContext` (theme light, then dark) and
  sends `ui/notifications/tool-result` with a real `submit_model_draft` result. The view did
  `ui/initialize` → `ui/notifications/initialized` → render → `ui/notifications/size-changed`,
  made no requests, logged no console errors, and followed the theme.
- Not done yet:
  - Claude web, which can't reach `127.0.0.1` and needs a public HTTPS MCP URL; that's the
    owner's decision.
