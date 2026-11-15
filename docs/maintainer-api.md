# Maintainer API

Authenticated part of the HTTP API (`docs/openapi.json`, tag `maintainer`). Every route needs
`Authorization: Bearer <token>`; tokens come from `PLUME_MAINTAINER_TOKENS` (a JSON list, e.g.
`'["pl_..."]'`). Without tokens configured the routes answer 503. Errors are
`{"error", "message", "detail"}`.

| Route | Does |
|---|---|
| `GET /v1/maintainer/me` | token check → `{"name": "maintainer"}` (401 on a bad token) |
| `POST /v1/packages` (multipart `file`, `.zip`) | stores and safely extracts the package, validates it → Job `uploaded` (201; 415 not a zip; 413 too large; 400 unreadable zip) |
| `GET /v1/jobs/{id}` | the Job |
| `POST /v1/jobs/{id}/review` `{apiId, displayName, tag}` | diff against the build `tag` points at, embedding plan (chunks not in the vector cache) → `reviewed` |
| `POST /v1/jobs/{id}/build` | runs the pipeline in the background (import → chunk → embed → facts → seal → eval gate), **no tag** → `building` → `staged` or `failed` |
| `GET /v1/jobs/{id}/events` | server-sent events, see below |
| `POST /v1/jobs/{id}/publish` | moves the tag to the staged build → `published`; **409 `gate_failed`** when the quality gate failed |
| `POST /v1/jobs/{id}/discard` | → `discarded` (not while building or after publish) |
| `GET /v1/jobs/{id}/dump` | the staged build as a `plume-dump` (`application/gzip`) |

Job states: `uploaded → reviewed → building → staged → published`, with `failed` (build again
from there) and `discarded`. Wrong-state calls answer 409 `invalid_state`.

## Events (SSE)

Each message has `id: <seq>`, `event: <type>` and `data: <JSON with the same id>`. Resume with
`Last-Event-ID`. The stream ends after `done` (or at once for a published/discarded job whose
events are drained).

| type | fields |
|---|---|
| `service` | `service` (`postgres`\|`gemini`), `detail` |
| `step` | `key` (`validate` `chunk` `diff` `embed` `store` `evaluate`), `status` (`running`\|`done`\|`failed`), `detail` |
| `progress` | `done`, `total`, `etaSeconds` (null) – embedding batches |
| `log` | `t` (ISO time), `source` (`plume`\|`postgres`\|`gemini`), `message` |
| `done` | `status` (`staged`\|`failed`), `message` |

## Quality gate

Gold sets are JSON files `<api>.json` in `PLUME_GOLD_DIRS` (format in
`src/plume/infrastructure/sources/gold_file.py`, examples in `tests/fixtures/gold/`). A build
fails the gate when recall@5 is below `PLUME_GATE_MIN_RECALL` (0.6), when a fact question is
wrong, when an expected document is missing, or when recall@5/MRR fall more than
`PLUME_GATE_MAX_DROP` (0.05) below the live build's eval on the same gold set. A failed build is
sealed but never tagged; `plume tag --force` overrides.
