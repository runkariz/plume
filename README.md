# Plume

Plume turns an API's documentation into a searchable, versioned knowledge base and serves it to
Claude (and any MCP client) so answers about the API come with citations.

- **Immutable builds.** Each import of an API's docs is a build: a draft that collects documents,
  then is sealed with a content hash and never changes again.
- **Tags.** `latest` (and later vendor versions) are movable pointers to sealed builds, like Docker
  tags. Publishing moves a tag; rolling back moves it back.
- **Hybrid search + exact facts.** Postgres with pgvector for vectors and full-text search, plus an
  exact index of endpoints, fields and scopes so "is this documented?" has evidence behind it.
- **MCP.** A read-only reader server for questions, a maintainer server for builds and tags.

Status: early. In place: ingest (read a connector package, chunk, embed, extract exact facts,
seal, tag), the reader (hybrid search, exact facts, documents, call checks) over HTTP and MCP,
the quality gate on gold questions, export/restore of builds, and the maintainer API (upload,
review, build with live events, publish). Canonical models and the web UI follow.

## Quick start

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
make install          # uv sync
make up               # Postgres 16 + pgvector on 127.0.0.1:18432
uv run plume --help
uv run plume migrate  # bring the schema to head
uv run plume load tests/fixtures/packages/test-catalog   # build -> seal -> tag latest
uv run plume builds test-catalog-api
make test             # architecture + unit tests
make test-int         # contract (Postgres) + integration tests (testcontainers)
make e2e              # against docker compose
make e2e-live         # live embeddings (needs PLUME_VERTEX_API_KEY or PLUME_GEMINI_API_KEY)
make lint             # ruff, mypy --strict, import-linter
```

Configuration comes from `PLUME_*` environment variables or a `.env` file; see `.env.example`.

## Ingest

`plume load <package>` reads a connector package (`connector/` with `app.json`, `endpoints/`,
`models/`, `knowledge/`, `auth/`, plus an optional `knowledge-export/` of cleaned page text) and
runs import -> chunk -> embed -> facts -> seal -> tag.

- **Build ids are derived from the input**: package hash, chunker version, embedding model and
  dimensions. Loading the same package again finds the sealed build and only moves the tag.
- **Document ids** are stable across vendor versions: endpoints are `endpoint:METHOD~/path` with
  the version segment replaced by `{version}`; models, guides and auth schemes are
  `model:<name>`, `guide:<id>`, `auth:<id>`.
- **Embeddings**: `PLUME_EMBEDDER=auto|hash|vertex|gemini`. `auto` uses Vertex AI express when
  `PLUME_VERTEX_API_KEY` is set, the Gemini API when `PLUME_GEMINI_API_KEY` is set, and otherwise
  an offline hashing embedder (not semantic; for development and CI). Vectors are 768-dim
  `halfvec`; unchanged chunks reuse cached vectors.
- **Facts**: every endpoint, documented field (path/query/header/body/response/model) and
  required scope, with the document and JSON pointer that state it, and `complete=false` when
  the source flags the schema as partial.
- `plume diff <old> <new>` lists added/changed/removed chunk ids; `plume tag <build> latest`
  publishes or rolls back.

## Quality gate, export and restore

```bash
uv run plume load <package> --gold tests/fixtures/gold/<api>.json   # exit 2 if the gate fails
uv run plume eval shopify --gold tests/fixtures/gold/shopify.json   # re-run the gate on latest
uv run plume export shopify --out shopify.plume.jsonl.gz           # verified, deterministic dump
uv run plume restore shopify.plume.jsonl.gz --tag latest           # one transaction, verified
make eval                                                           # gold sets of the fixtures
```

A dump is gzipped JSON lines (manifest, documents, chunks with vectors, facts). Restore checks
every chunk hash against the build's sealed content hash before writing anything. Maintainers
can drive the same flow over HTTP: see [docs/maintainer-api.md](docs/maintainer-api.md).

## Serve and connect Claude

```bash
make up                         # Postgres + API (127.0.0.1:18480) + MCP (127.0.0.1:18481/mcp)
claude mcp add --transport http plume http://127.0.0.1:18481/mcp
```

Or install the Claude Code plugin from this repository's marketplace (MCP config + a skill that
tells Claude how to cite and when absence is proven):

```
/plugin install plume --marketplace <owner>/plume
```

Run the servers without Docker: `uv run plume serve` (HTTP) and `uv run plume mcp` (MCP). The
HTTP contract is [docs/openapi.json](docs/openapi.json) (`uv run plume openapi`); the MCP tools
are in [docs/mcp-tools.md](docs/mcp-tools.md); the input package format is in
[docs/package-contract.md](docs/package-contract.md).

## Layout

Clean architecture, enforced by import-linter (`.importlinter`) and `tests/architecture`:

```
src/plume/
  domain/          entities and rules, standard library only
  application/     use cases and ports (typing.Protocol)
  infrastructure/  adapters: Postgres, Alembic, settings
  interfaces/      CLI (Typer), HTTP (FastAPI), MCP reader server
  bootstrap/       composition root
```

See [docs/adr/0001-clean-architecture.md](docs/adr/0001-clean-architecture.md).

## Ports

Plume uses the 18400–18499 block: Postgres 18432, HTTP API 18480, MCP 18481, web dev server 18473.

## License

MIT, see [LICENSE](LICENSE).
