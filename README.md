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

Status: early. Slice 1 (the skeleton) is in place: layers, settings, the build/tag domain, the
database migrations and the CLI. Ingest, search, MCP and the web UI follow.

## Quick start

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
make install          # uv sync
make up               # Postgres 16 + pgvector on 127.0.0.1:18432
uv run plume --help
uv run plume migrate  # bring the schema to head
make test             # architecture + unit tests
make test-int         # integration tests (testcontainers)
make lint             # ruff, mypy --strict, import-linter
```

Configuration comes from `PLUME_*` environment variables or a `.env` file; see `.env.example`.

## Layout

Clean architecture, enforced by import-linter (`.importlinter`) and `tests/architecture`:

```
src/plume/
  domain/          entities and rules, standard library only
  application/     use cases and ports (typing.Protocol)
  infrastructure/  adapters: Postgres, Alembic, settings
  interfaces/      CLI (Typer); later HTTP and MCP
  bootstrap/       composition root
```

See [docs/adr/0001-clean-architecture.md](docs/adr/0001-clean-architecture.md).

## Ports

Plume uses the 18400–18499 block: Postgres 18432, HTTP API 18480, MCP 18481, web dev server 18473.

## License

MIT, see [LICENSE](LICENSE).
