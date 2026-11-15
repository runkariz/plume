# Canonical models

Plume builds a canonical model of one concept (Order, Product, ...) across 2..6 APIs. A model is
written either by the user's Claude from an evidence pack, or (maintainers only) by Plume's own
LLM. Either way Plume checks every citation against the pinned builds before it stores an
immutable snapshot (status `generated_unverified`). Plume never invents knowledge: every
mapping needs a verbatim quote from a document of the pinned build. Mapping *code* stays with
Claude.

```
suggest_concepts(apis, q?, only?, require?, limit?, offset?)
                                    deterministic: concepts, coverage per API, a factual reason
start_model_session(apis, concept)  pins the current build of each API
get_model_context(session_id)       index of the evidence, the draft format and the rules
get_model_evidence(session_id, api) the fields with descriptions, paged (next_cursor)
submit_model_draft(session_id, d[, based_on])  validated -> snapshot | refused with codes
revise_model(snapshot_id)           a session on the current builds, the model as starting draft
get_model(snapshot_id)              the stored model with its versions and link
```

## Concept suggestions

`POST /v1/models/suggest` (and the maintainer MCP `suggest_concepts`) lists the concepts the
selected APIs document, with no LLM. A concept is a normalised, singular resource or model name
(`Orders`, `order` → `Order`; `Taxes` → `Tax`). Per API it is `direct` (an endpoint resource
or a model has that name), `derived` (only field names mention it) or `absent`. A concept needs
at least one `direct` API: field words alone never make one. Generic and timestamp words
(`Updated`, `Attributes`, `Entities`, `Date`, `Page`, `Value`, ...) are never concepts, even
as model names.

- All concepts, paged: `limit` (default 24, max 100), `offset`, `total`, `nextOffset`. Order:
  most `direct` APIs, then most present, then likely fields.
- `only`: `multi` (default; present in 2+ selected APIs), `single` (present in exactly one),
  `all`. `q`: text over name, id and reason. `require`: API ids where the concept must be direct
  or derived. `inAll`, `writeOnly`: present in every API / has create-update-delete endpoints.
- `counts {all, inAll, write, single}` honour `q` and `require` (for the filter chips).
- Each concept: `coverage`, `operations`, `difficulty`, `likelyFields`, `documents` per API,
  `apiCounts {api: {models, endpoints, operations, fields}}`, and `reason`: one paragraph built
  from those counts, e.g. "Shopify has an Order model and 30 order endpoints (read, create,
  update, delete); ... About 532 fields are likely to map. Straightforward because every API
  documents Order directly."

## Who sees what

| Visibility | Written by | Readable by | Listed |
|---|---|---|---|
| `official` | a maintainer, then released | anyone | yes (`GET /v1/models`, `list_models`) |
| `unreleased` | a maintainer (their Claude or `generate_model`) | maintainers only (404 otherwise) | maintainer lists |
| `unlisted` | anyone (no token) | anyone with the id: the id **is** the share link | never; the owner lists their own with owner keys |
| `discarded` | an unreleased model a maintainer threw away | maintainers only | maintainer lists |

- **Users** (no auth, rate limited): any number of models over any 2..6 APIs. Each submit that
  starts a new model returns an `ownerKey` once (`pk_…`, stored only as a SHA-256). The Claude
  plugin keeps the keys and ids in `~/.plume/models.json`; `list_my_models(owner_keys)` /
  `POST /v1/models/mine` returns the latest version of each. A lost key loses nothing but the
  listing: links keep working. Unlisted ids are `u-` + 128 random bits (not a content hash: a
  hash can be computed from the content, and two users with the same draft would share it).
- **Maintainers** (bearer token): drafts are stored `unreleased`; `release` makes one official,
  `discard` throws it away (both 409 `invalid_state` unless the model is unreleased). Nothing
  becomes official without a release. Maintainer ids are content hashes (`m-…`), so the same
  draft on the same builds is the same snapshot.
- Models that existed before visibility was introduced (migration 0007) are official v1.

## Versions (lineages)

A model never changes; a change is a new version. `revise_model(id)` opens a session pinned to
the APIs' **current** builds with the model as `starting_draft`; submitting with
`based_on=id` stores the next version. `lineage` in the model JSON gives `{id, version,
versions, basedOn, latestId, history[]}` (unreleased/discarded versions appear only for
maintainers).

- A user revising an **unlisted** model adds a version to that lineage (anyone with the link may).
- A user revising an **official** model starts a new unlisted lineage `basedOn` it (with a new
  owner key): users never add versions to an official lineage.
- A maintainer revising an official or unreleased model adds an unreleased version to that
  lineage; releasing it makes it the current official version (public lists show the latest
  official version of each lineage).

## Server-side generation (maintainers)

`POST /v1/models/generate` with the token (engine `server`, the default with a token) or the
maintainer MCP `generate_model(apis, concept)` starts a job. Plume builds the evidence pack
(all fields of the concept's documents, up to ~200k characters), asks the LLM for one JSON
draft, and runs the **same** validation. A refused draft goes back to the LLM with the issues,
for up to `PLUME_MODEL_MAX_ROUNDS` rounds (default 3). The accepted model is stored unreleased
with `generator: "gemini:<model>"`.

- LLM: Gemini on Vertex AI express mode (`generateContent`), behind the `ModelWriter` port (a
  scripted fake in tests). Model `PLUME_MODEL_LLM` (default `gemini-4-argon`, the owner's choice; not yet confirmed against the Vertex express
  endpoint: the first live run must, and reports a missing model as an error, never falling back).
- Key: `PLUME_VERTEX_KEY_FILE`, a file read on every call and sent only in the
  `x-goog-api-key` header; never logged, never in an error. Unset or unreadable: generation
  answers 503 `llm_unavailable` and the web offers the Claude flow instead.
- Progress: `GET /v1/models/jobs/{id}` and SSE `GET /v1/models/jobs/{id}/events` (token;
  `Last-Event-ID` resumes; jobs and events are in Postgres). Events: `queued {jobId}`,
  `started {apis, concept}`, `context {documents, fields}`, `round {n, of}`,
  `refused {round, issues[{code, field, api, message}]}`, `accepted {snapshotId, round}`,
  `failed {code, message}`, `done {status, snapshotId}`. Jobs interrupted by a restart are
  marked failed at startup.

## Draft format

See `draft_format` in the evidence pack and `tests/fixtures/drafts/catalog-order-good.json`.
Each canonical field lists, per API, `paths` (documented field names copied from the
evidence), optional `fetch` ("METHOD /path"), `join`, `transform`, and `evidence`
(`doc_id` + a verbatim `quote`). A mapping with `transform`, `join` or several paths counts
as **derived**; otherwise **supported**; an API missing from a field is **unsupported**.

## Validation (refusal codes)

| Code | Meaning |
|---|---|
| `INVALID_FORMAT` | the JSON does not have the draft shape, or is over 1,000,000 characters |
| `API_NOT_IN_SESSION` | a mapping names an API that is not in the session |
| `MISSING_CITATION` | a mapping has no evidence |
| `DOC_NOT_FOUND` | the cited document is not in that API's pinned build |
| `QUOTE_NOT_FOUND` | the quote is not in the cited document (case/whitespace-insensitive) |
| `FIELD_NOT_FOUND` | a source path is not a documented field of that API |
| `ENDPOINT_NOT_FOUND` | the `fetch` endpoint is not documented in that API |
| `NO_SOURCES` | a canonical field maps no API |

A refused draft stores nothing. Fix and resubmit. Submitting the same draft again in the same
session returns the stored model (`created: false`). Snapshot content is never updated: a
database trigger refuses any UPDATE except `visibility` / `released_at`.

## Where

- Reader MCP (public, rate limited): `start_model_session`, `get_model_context`,
  `get_model_evidence`, `submit_model_draft`, `get_model_session`, `revise_model`,
  `get_model`, `list_models` (official), `list_my_models`.
- Maintainer MCP (bearer token): `http://127.0.0.1:18481/maintainer/mcp`
  (`claude mcp add --transport http plume-maintainer http://127.0.0.1:18481/maintainer/mcp
  --header "Authorization: Bearer <token>"`): the same model tools (storing unreleased),
  `suggest_concepts`, `list_models(api, visibility)`, `release_model`, `discard_model`,
  `generate_model`, `get_generation`, `publish_build`, `get_job`.
- HTTP (see [openapi.json](openapi.json)); token routes in **bold**:
  - `GET /v1/models/candidates`, `POST /v1/models/suggest`
  - `POST /v1/models/generate {apis, concept, engine?, force?}`: engine `claude` → a session
    (`ready` + `snapshotId` when a model the caller may see already exists for the current
    builds: official, or unreleased for a maintainer; never an unlisted one); **engine
    `server`** → 202 job.
  - `GET /v1/models/sessions/{id}` (state for pollers: `open` | `submitted` + `snapshotId`),
    `.../context`, `.../evidence`, `POST .../draft?basedOn=` (201 `{created, visibility,
    ownerKey, model}`; unlisted without the token, unreleased with it).
  - `GET /v1/models` (official; **`?visibility=unreleased|all`**), `GET /v1/models/{id}`,
    `POST /v1/models/{id}/revise`, `POST /v1/models/mine {ownerKeys}`.
  - **`POST /v1/models/{id}/release`**, **`POST /v1/models/{id}/discard`**,
    **`GET /v1/models/jobs/{id}`**, **`GET /v1/models/jobs/{id}/events`**.
  - Errors `{error, message}`: 401 `unauthorized` (missing/wrong token on a token route, or a
    wrong token anywhere), 404 `not_found` (also for unreleased models without the token),
    409 `invalid_state`, 422 `draft_refused` (+ `issues`), 429 `rate_limited`, 503
    `llm_unavailable`, 502 `llm_failed`.
- Model JSON adds `visibility`, `official`, `origin` (`user` | `maintainer`), `generator`,
  `releasedAt`, `basedOn`, `lineage`, `sharePath` (`/models/{id}`, the web route), `shareUrl`
  (`PLUME_WEB_PUBLIC_URL` + sharePath, or null) and `revisePrompt` (text for "modify with
  Claude").
