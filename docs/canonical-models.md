# Canonical models

Plume builds a canonical model of one concept (Order, Product, ...) across 2..6 APIs. Plume does
not run an LLM: Claude writes the model from an evidence pack, and Plume checks every citation
against the pinned builds before it stores an immutable snapshot (status
`generated_unverified`). Mapping *code* stays with Claude.

```
suggest_concepts(apis)            deterministic: shared resources/models, coverage per API
start_model_session(apis, concept) pins the current build of each API
get_model_context(session_id)     evidence pack: per API the concept's documents + fields,
                                  the draft format and the rules
submit_model_draft(session_id, d) validated -> snapshot | refused with issue codes
get_model(snapshot_id)            the stored model (also GET /v1/models/{id})
```

## Draft format

See `draft_format` in the evidence pack and `tests/fixtures/drafts/catalog-order-good.json`.
Each canonical field lists, per API, `paths` (documented field names copied from the
evidence), optional `fetch` ("METHOD /path"), `join`, `transform`, and `evidence`
(`doc_id` + a verbatim `quote`). A mapping with `transform`, `join` or several paths counts
as **derived**; otherwise **supported**; an API missing from a field is **unsupported**.

## Validation (refusal codes)

| Code | Meaning |
|---|---|
| `INVALID_FORMAT` | the JSON does not have the draft shape |
| `API_NOT_IN_SESSION` | a mapping names an API that is not in the session |
| `MISSING_CITATION` | a mapping has no evidence |
| `DOC_NOT_FOUND` | the cited document is not in that API's pinned build |
| `QUOTE_NOT_FOUND` | the quote is not in the cited document (case/whitespace-insensitive) |
| `FIELD_NOT_FOUND` | a source path is not a documented field of that API |
| `ENDPOINT_NOT_FOUND` | the `fetch` endpoint is not documented in that API |
| `NO_SOURCES` | a canonical field maps no API |

A refused draft stores nothing. Fix and resubmit; the same pinned builds + the same model give
the same snapshot id (idempotent). Snapshots are never updated (enforced in the database too).

## Where

- Maintainer MCP (bearer token): `http://127.0.0.1:18481/maintainer/mcp`
  (`claude mcp add --transport http plume-maintainer http://127.0.0.1:18481/maintainer/mcp
  --header "Authorization: Bearer <token>"`): all tools above plus `list_models`,
  `publish_build`, `get_job`.
- Reader MCP (public): `get_model`, `list_models`.
- HTTP: `GET /v1/models/candidates`, `POST /v1/models/suggest`, `POST /v1/models/generate`
  (opens a session; returns an existing snapshot id when one matches the current builds),
  `GET /v1/models/sessions/{id}/context`, `POST /v1/models/sessions/{id}/draft` (token),
  `GET /v1/models`, `GET /v1/models/{id}`.

Open owner decision (see the plan): whether the Plume server should also run an LLM for
signed-in users. Today only the user's Claude generates.
