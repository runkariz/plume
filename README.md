# Plume

Plume turns an API's documentation into a searchable, versioned knowledge base and serves it to
Claude (and any MCP client), so answers about the API come with citations instead of guesses.

- **Builds and tags.** Each import of an API's docs is an immutable, sealed build. `latest` is a
  movable tag: publishing moves it, rolling back moves it back.
- **Search and exact facts.** Hybrid search (pgvector + Postgres full text) plus an exact index of
  every documented endpoint, field and scope, so "is this documented?" has evidence, and
  "not documented" is only said when the sources were complete.
- **Quality gate.** Gold questions per API; a build that answers worse than the live one is not
  published.
- **Canonical models.** Claude maps one concept (Order, Product…) across 2–6 APIs; Plume checks
  every citation against the docs and stores the result as an immutable snapshot.
- **Interfaces.** MCP (reader + maintainer), an HTTP API, a CLI, a Claude Code plugin and a web UI.

Status: early, working end to end on Shopify, WooCommerce and Mirakl packages. Open source (MIT).

## Quick start (from zero, about 5 minutes)

You need Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), and, for the web UI, Node 24.

**1. Start the stack** (Postgres + pgvector, the HTTP API, the MCP server):

```bash
git clone <this repository> plume && cd plume
make install                                   # uv sync (the CLI runs on the host)
export PLUME_EMBEDDER=hash                     # offline embeddings; see "Real embeddings" below
export PLUME_MAINTAINER_TOKENS='["pl_change_me_to_a_long_random_token"]'   # >= 16 chars
make up                                        # API 127.0.0.1:18480, MCP 127.0.0.1:18481
```

**2. Load an API.** A sample package ships with the tests:

```bash
uv run plume load tests/fixtures/packages/shopify-mini --gold tests/fixtures/gold/shopify.json
uv run plume apis                              # shopify  shopify  e-commerce
```

`load` reads the package, chunks and embeds it, extracts the facts, seals the build, runs the
gold questions and moves `latest` to it.

**3. Ask something** over HTTP:

```bash
curl -s -X POST 127.0.0.1:18480/v1/apis/shopify/search \
  -H 'content-type: application/json' -d '{"query": "list products", "topK": 3}'
curl -s -X POST 127.0.0.1:18480/v1/apis/shopify/find-fact \
  -H 'content-type: application/json' -d '{"name": "since_id"}'
```

**4. Connect Claude Code.**

```bash
claude mcp add --transport http plume http://127.0.0.1:18481/mcp
```

or load the plugin (MCP config + skills that make Claude use Plume and cite it):

```bash
claude --plugin-dir ./plugin        # or /plugin install plume --marketplace <owner>/plume
```

Then ask, e.g. "In Shopify, which scope do I need to list assigned fulfillment orders?".
Claude Desktop/web: add `http://127.0.0.1:18481/mcp` as a custom connector (a local URL only
works where that host can reach it).

**5. Open the web UI** (browse, try search, the maintainer wizard, canonical models):

```bash
cd web && cp .env.example .env.local
# in .env.local: VITE_API_BASE_URL=http://127.0.0.1:18480 and VITE_USE_MOCKS=false
npm ci && npm run dev                          # http://127.0.0.1:18473
```

Sign in to **Maintainer** with the token from step 1. More in [web/README.md](web/README.md).

For a shared or long-running deployment, serve the built web UI and the API from **one
origin**: a reverse proxy serves `web/dist` and forwards `/v1/` to the API (build the web with
`VITE_API_BASE_URL` set to that same origin). Cross-origin API calls depend on
`PLUME_CORS_ORIGINS` and are blocked by some embedded browsers (e.g. Claude's browser pane);
same-origin needs no CORS at all. A minimal nginx block:

```nginx
location /v1/ {
  proxy_pass http://127.0.0.1:18480;
  proxy_set_header Host $host;
  proxy_buffering off;  # build and generation progress are event streams
}
location /    { root /srv/plume-web; try_files $uri /index.html; }
```

Stop with `make down` (data is kept in a Docker volume).

## Add your own API

Plume reads a **connector package**: a folder with `connector/` (and optionally
`knowledge-export/`), in the format produced by Kariz stream (contract `schemaVersion` 1.x).

```
my-api/
  connector/
    package.json            {"schemaVersion": "1.2"}
    app.json                name, summary, docLink, category, apiVersioning, errorFormat
    endpoints/<id>/request.json   method, url, name, description, responses, requiredScopes…
                  params.schema.json  variables.schema.json  body.schema.json
                  responses/200.schema.json
    models/<name>.schema.json     JSON schema (x-complete: false = partial)
    knowledge/<id>.json + <id>.md guides
    auth/<id>.json                auth schemes and their scopes
  knowledge-export/**/*.md        optional cleaned page text (front matter source_url)
```

The exact fields, and what Plume ignores, are in
[docs/package-contract.md](docs/package-contract.md). Check a package before loading it:

```bash
PLUME_CONTRACT_PACKAGES=/path/to/my-api uv run pytest tests/contract/test_package_contract.py
```

Then either load it with the CLI (`uv run plume load /path/to/my-api`) or upload it as a `.zip`
in the web UI's maintainer wizard (upload → review the diff and embedding plan → build with
live progress → publish). The API id comes from `app.json` `name` (slugged).

- **Gate it.** If the package has `knowledge-export/gold-questions.json`, convert it with
  `uv run plume gold-import <package> --out <api>.json`. Or write a gold set `<api>.json` (search questions with the expected document ids,
  plus present/absent facts; see `tests/fixtures/gold/`) and load with `--gold`, or put it in a
  folder listed in `PLUME_GOLD_DIRS` (the compose API mounts `tests/fixtures/gold`, override
  with `PLUME_GOLD_DIR`). A failing build is sealed but not published (`plume load` exits 2).
- **Update it.** Load the new package; unchanged chunks reuse their vectors. `plume diff <old>
  <new>` shows what changed; `plume tag <build> latest` rolls back.
- **Share it.** `plume export <api> --out x.plume.jsonl.gz` writes a verified dump; `plume restore`
  loads it anywhere in one transaction.

## Real embeddings

The offline `hash` embedder needs no key but is not semantic. For real search quality use
Gemini embeddings (768 dims), with either key:

```bash
export PLUME_EMBEDDER=vertex PLUME_VERTEX_API_KEY=...     # Vertex AI express mode
# or: export PLUME_EMBEDDER=gemini PLUME_GEMINI_API_KEY=... # Gemini API
make up && uv run plume load <package>
```

The CLI that loads and the servers that answer must use the same embedder: a build remembers its
embedding model, and search refuses to mix models (full-text mode still works). Changing the
embedder means loading the packages again.

## What a build contains

| Item | From the package | Used for |
|---|---|---|
| Endpoint documents (`endpoint:GET~/admin/api/{version}/products.json`) | `endpoints/*/request.json` + schemas | search, `get_document`, `check_call` |
| Model documents (`model:<name>`) | `models/*.schema.json`; bundler titles like `A01_Response_200_X` get readable names | search, facts, canonical models |
| Guides, auth, app | `knowledge/`, `auth/`, `app.json`, `knowledge-export/` | search |
| Facts | every endpoint, field (path/query/header/body/response/model) and scope, with a JSON pointer | `find_fact`, model validation |
| Chunks + vectors | documents split by size/headings | hybrid search |
| Eval | your gold set | the gate, the quality shown in the UI |

Ids never contain the vendor's version, so the same endpoint keeps its id across vendor
releases. See [docs/package-contract.md](docs/package-contract.md).

## Reference

**CLI** (`uv run plume --help`): `migrate`, `load`, `apis`, `builds`, `diff`, `tag`, `eval`,
`gold-import`, `export`, `restore`, `serve` (HTTP), `mcp` (MCP), `openapi`.

**HTTP**: [docs/openapi.json](docs/openapi.json) (also served at `/openapi.json` and `/docs`).
Besides search and facts, each API exposes what its package contains, verbatim:
`/v1/apis/{api}/items?kind=&tag=` (every id resolves at `/documents/{id}`, with the source JSON as
`raw`), `/auth`, `/triggers` (events + the webhook mechanism), `/environments`, `/mcp` (the vendor's
MCP server, when it has one) and `/icon`; an absent section says so.
Reader routes are public and rate limited; maintainer routes need `Authorization: Bearer
<token>`: [docs/maintainer-api.md](docs/maintainer-api.md).

**MCP**: reader at `/mcp` (public, read-only), maintainer at `/maintainer/mcp` (bearer token):
[docs/mcp-tools.md](docs/mcp-tools.md). Canonical models: [docs/canonical-models.md](docs/canonical-models.md).

**Configuration** (`PLUME_*` environment variables or a `.env` file; see `.env.example`):

| Variable | Default | |
|---|---|---|
| `PLUME_DATABASE_URL` | `postgresql+psycopg://plume:plume@127.0.0.1:18432/plume` | |
| `PLUME_EMBEDDER` | `auto` | `auto`, `hash`, `vertex`, `gemini` (`auto`: Vertex key, else Gemini key, else hash) |
| `PLUME_VERTEX_API_KEY` / `PLUME_GEMINI_API_KEY` | – | never logged |
| `PLUME_VERTEX_KEY_FILE` | – | the Vertex key as a file (read when used, never logged): for embeddings and generation, so no key sits in a container's env |
| `PLUME_MAINTAINER_TOKENS` | `[]` | list (JSON `["a","b"]` or comma-separated `a,b`), each ≥ 16 chars; empty = maintainer API off (503) |
| `PLUME_GOLD_DIRS` | `[]` | folders of `<api>.json` gold sets |
| `PLUME_GATE_MIN_RECALL` / `PLUME_GATE_MAX_DROP` | `0.6` / `0.05` | the quality gate |
| `PLUME_GATE_MIN_RECALL_BY_EMBEDDER` | `{}` | per-embedder recall floor, e.g. `{"vertex": 0.75}`; others use `PLUME_GATE_MIN_RECALL` |
| `PLUME_READER_RATE_LIMIT_PER_MINUTE` | `120` | per client address; `0` = off |
| `PLUME_TRUSTED_PROXY_HOPS` | `0` | behind N proxies that append to `X-Forwarded-For`, the limiter counts the Nth entry from the right (e.g. `client, traefik` with `2` → `client`); `0` = the TCP peer. See docs/security.md |
| `PLUME_CORS_ORIGINS` | the web dev server | list (JSON or comma-separated) |
| `PLUME_MCP_ALLOWED_HOSTS` | loopback | Host headers the MCP server accepts; list (JSON or comma-separated), e.g. `plume.example.com,plume.example.com:443` |
| `PLUME_MCP_DEBUG` | `false` | log each MCP request's method (initialize: client, protocol, MCP Apps declared; `ui://` reads; tool names). No arguments, results or tokens |
| `PLUME_MCP_CORS_ORIGINS` | `[]` | browser origins allowed to call the MCP endpoints (browser-based MCP clients such as the ext-apps basic-host); off by default |
| `PLUME_DATA_DIR` | `.plume` (`/data` in Docker) | uploads and dumps |
| `PLUME_MAX_UPLOAD_BYTES` | 200 MiB | package uploads |
| `PLUME_VERTEX_AUTH` | `auto` | `key` (`PLUME_VERTEX_API_KEY` / `PLUME_VERTEX_KEY_FILE`), `adc` (Application Default Credentials, e.g. Workload Identity on GKE; needs `PLUME_VERTEX_PROJECT`), `auto` = a key if one is set, else ADC with a project. With ADC also set `PLUME_EMBEDDER=vertex` |
| `PLUME_EVIDENCE_BUDGET_CHARS` | `200000` | API evidence server generation sends the model, shared fairly by the APIs (~4 characters per prompt token); raise it for big models (e.g. `500000`) |
| `PLUME_VERTEX_EMBED_LOCATION` | `global` | the embedding model's location on the project path (whenever `PLUME_VERTEX_PROJECT` is set, key or ADC), e.g. `europe-west3` to keep query text in the EU |
| `PLUME_VERTEX_PROJECT` / `PLUME_VERTEX_LOCATION` | – / `global` | with a project, generation calls the model at that location (gemini-4-argon answers only at `global`); without one, the location-less express URL |
| `PLUME_MODEL_LLM` / `PLUME_MODEL_MAX_ROUNDS` | `gemini-4-argon` / `3` | the generation model and its repair rounds |
| `PLUME_MCP_APP_HTML` | the packaged file | the MCP App bundle (model view) served as `ui://plume/model-view`; see [docs/mcp-apps.md](docs/mcp-apps.md) |
| `PLUME_WEB_PUBLIC_URL` | – | the web UI's base URL; model share links are `<this>/models/{id}` |

Compose host ports: `PLUME_PG_HOST_PORT` (18432), `PLUME_API_HOST_PORT` (18480),
`PLUME_MCP_HOST_PORT` (18481). Plume keeps to the 18400–18499 block.

Security notes and known limits: [docs/security.md](docs/security.md).

## Deploying in containers

- **One image, several commands**: `serve` (HTTP API, 18480), `mcp` (MCP, 18481), `migrate`,
  `load`, `restore`. The image sets `PLUME_API_HOST` and `PLUME_MCP_HOST` to `0.0.0.0` (outside
  a container both default to `127.0.0.1`). Both processes answer `GET /health` (no auth, not
  rate limited) for probes; the image's HEALTHCHECK tries both ports.
- **Kubernetes service links**: a Service named `plume-api` or `plume-mcp` makes Kubernetes
  inject `PLUME_API_PORT=tcp://…` into pods, which collides with Plume's `PLUME_` settings
  (Plume refuses to start and says so). Set `enableServiceLinks: false` on the pods, or name
  the Services differently.
- **Lists in env vars** (`PLUME_MAINTAINER_TOKENS`, `PLUME_MCP_ALLOWED_HOSTS`,
  `PLUME_MCP_CORS_ORIGINS`, `PLUME_CORS_ORIGINS`, `PLUME_GOLD_DIRS`): a JSON list or a
  comma-separated string.
- **Behind a proxy**: `PLUME_TRUSTED_PROXY_HOPS`, outbound hosts and the Vertex modes are in
  [docs/security.md](docs/security.md); `PLUME_MCP_ALLOWED_HOSTS` must list the public host.

## Development

```bash
make lint       # ruff, ruff format --check, mypy --strict, import-linter
make test       # architecture + unit + contract (fakes); no Docker, a few seconds
make test-int   # contract (Postgres) + integration, via testcontainers
make e2e        # its own compose project (ports 18434/18484/18485), torn down afterwards
make eval       # the gold sets of the fixtures through the gate
make e2e-live   # live embeddings (needs a key)
make e2e-live-claude   # Claude Code as the client, opt-in and billed: docs/level2.md
```

Clean architecture, enforced by import-linter (`.importlinter`) and `tests/architecture`:

```
src/plume/
  domain/          entities and rules (builds, tags, facts, eval, canonical models); stdlib only
  application/     use cases and ports (typing.Protocol)
  infrastructure/  adapters: Postgres/pgvector, Alembic, embedders, package reader, dumps, settings
  interfaces/      CLI (Typer), HTTP (FastAPI), MCP servers
  bootstrap/       composition root
web/               React UI (talks only to the HTTP API)
plugin/            Claude Code plugin (MCP config + skills); .claude-plugin/marketplace.json
```

See [docs/adr/0001-clean-architecture.md](docs/adr/0001-clean-architecture.md).

## Docs

| | |
|---|---|
| [package-contract.md](docs/package-contract.md) | what Plume reads from a package, what it ignores |
| [mcp-tools.md](docs/mcp-tools.md) | MCP tools, reader and maintainer |
| [maintainer-api.md](docs/maintainer-api.md) | jobs, uploads, live events, publish, the gate |
| [canonical-models.md](docs/canonical-models.md) | sessions, evidence, draft format, refusal codes |
| [security.md](docs/security.md) | surface, controls, known gaps |
| [level2.md](docs/level2.md) | Claude Code as the client (harness) |
| [openapi.json](docs/openapi.json) | the HTTP contract |

## License

MIT, see [LICENSE](LICENSE).
