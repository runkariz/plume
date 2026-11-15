# MCP tools

Reader server: streamable HTTP at `http://127.0.0.1:18481/mcp` (`plume mcp`). Read-only, no auth,
DNS-rebinding protection (allowed hosts from `PLUME_MCP_ALLOWED_HOSTS`). Every result includes
`api`, `build`, `tag` and `docs_as_of`. `version` defaults to the `latest` tag; a build id pins.

| Tool | Arguments | Returns |
|---|---|---|
| `list_apis` | – | APIs with latest build, tags, counts |
| `search_docs` | `api, query, kind?, top_k?, version?` | hybrid (vector + full-text, RRF) hits, one per document |
| `get_document` | `api, doc_id, version?` | full text, fields, source URL, anchor, citation |
| `find_fact` | `api, name, kind?, owner?, resource?, location?, version?` | exact matches with evidence, or `found:false` with `checked`, `complete`, `text_mentions` and the wording to use |
| `check_call` | `api, method, path, params?, version?` | `documented` / `not_documented`, matched endpoint, per-param location |
| `list_builds` | `api` | builds (newest first) with tags |
| `diff_builds` | `api, from_version, to_version?, limit?` | added / changed / removed chunk ids |
| `list_auth_schemes` / `get_auth_scheme` | `api[, scheme_id], version?` | auth schemes as the package states them; detail = the auth JSON + variables schema verbatim |
| `list_triggers` / `get_trigger` | `api[, key], version?` | trigger events / webhook topics; `present: false` when the package has none |
| `get_environments` | `api, version?` | environments, base URLs, versioning and the variables schema, verbatim |
| `get_vendor_mcp` | `api, version?` | the vendor's own MCP server(s) and tools when the package lists them; `present: false` otherwise |
| `suggest_related` | `apis, concept, limit?, offset?` | related concepts with relation candidates (documented evidence only, cited per API) and the designs it supports; `aliases` for differently named concepts at the same position. The user decides |
| `start_model_session` | `apis, concept` | a session pinned to the current builds (2..6 APIs) |
| `get_model_context` / `get_model_evidence` | `session_id[, api, doc_ids?, cursor?]` | the evidence index; the fields, paged |
| `submit_model_draft` | `session_id, draft, based_on?` | validated → stored **unlisted** (`share_url`, `owner_key` once for a new model, `version`) or refused with issue codes |
| `get_model_session` | `session_id` | `open` / `submitted` + `snapshot_id` |
| `revise_model` | `snapshot_id` | a new session on the current builds with the model as `starting_draft` |
| `get_model` | `snapshot_id` | a model (official or unlisted) with `lineage`, `shareUrl`, `revisePrompt` |
| `list_models` | `api?` | official models (latest version of each), newest first |
| `list_my_models` | `owner_keys` | the latest version of each model started with those keys |

## Maintainer server

`http://127.0.0.1:18481/maintainer/mcp`, `Authorization: Bearer <token>` (401 without; 503 when
no tokens are configured). Tools: `suggest_concepts(apis, q?, only?, require?, limit?,
offset?)` (paged; see canonical-models.md), the model tools above except
`list_my_models` (drafts are stored **unreleased**; `get_model` also shows unreleased models),
`list_models(api?, visibility="all")` (official | unreleased | unlisted | all),
`release_model`, `discard_model`, `generate_model(apis, concept)` (Plume's LLM; returns a job),
`get_generation(job_id)`, `publish_build`, `get_job`. See
[canonical-models.md](canonical-models.md).

The same use cases back the HTTP API (`docs/openapi.json`); `POST /v1/apis/{api}/search`
returns the exact MCP payload as `claudePayload`.

Absence rule: say "not documented in build X" only when `find_fact` returns `found:false` and
`complete:true`; with `complete:false` absence is not proven.

## MCP Apps

Both servers serve `ui://plume/model-view` (`text/html;profile=mcp-app`). `get_model`,
`submit_model_draft` (and on the maintainer server `release_model`, `discard_model`,
`get_generation`) point at it with `_meta.ui.resourceUri`, so Claude web/Desktop show the model
inline; text-only hosts get a summary and the link. Write tools are `visibility: ["model"]`.
See [mcp-apps.md](mcp-apps.md).
