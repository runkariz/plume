# ADR 0001: Clean architecture with enforced layers

- Status: accepted
- Date: 2026-11-15

## Context

Plume has several entry points (CLI, HTTP API, MCP servers, a worker) over the same rules: builds
are immutable once sealed, tags point only at sealed builds, answers must cite their sources. It
also has several replaceable backends (Postgres/pgvector, Gemini or Vertex embeddings, local or
GitHub-release dumps). Without a firm boundary, business rules leak into handlers and adapters,
and the HTTP and MCP surfaces drift apart.

## Decision

Four layers plus a composition root:

| Layer | May import | Holds |
|---|---|---|
| `domain` | standard library only | entities and rules as frozen dataclasses |
| `application` | `domain` | one use case per class (`execute()`), ports as `typing.Protocol` |
| `infrastructure` | `application`, `domain` | adapters implementing ports; `settings.py`, the only env reader |
| `interfaces` | `application`, `domain` | CLI, HTTP, MCP, worker: parse, call one use case, map |
| `bootstrap` | everything | wires adapters into use cases for each entry point |

`interfaces` and `infrastructure` never import each other. HTTP and MCP call the same use cases.

Enforcement: import-linter contracts in `.importlinter` (layers, a pure domain, a framework-free
application, interfaces without infrastructure), run by `make lint` and by
`tests/architecture/test_layers.py`, which also checks that the domain and application import only
the standard library and inner layers, and that only `settings.py` reads the environment.

## Consequences

- Use cases are tested with in-memory fakes of the ports (`tests/fakes`); the fakes define the
  reference behaviour, and contract tests run the same suite against the real adapters.
- Pydantic appears only in `infrastructure` (settings) and `interfaces` (request schemas).
- Adding an entry point means a new `interfaces` module and a new wiring in `bootstrap`; no use
  case changes.
- A little more ceremony (ports, factories) than a flat app; accepted for testability.
