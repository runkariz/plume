# MCP tools

Reader server: streamable HTTP at `http://127.0.0.1:18481/mcp` (`plume mcp`). Read-only, no auth,
DNS-rebinding protection (allowed hosts from `PLUME_MCP_ALLOWED_HOSTS`). Every result includes
`api`, `build`, `tag` and `docs_as_of`. `version` defaults to the `latest` tag; a build id pins.

| Tool | Arguments | Returns |
|---|---|---|
| `list_apis` | – | APIs with latest build, tags, counts and `notices` [{code, section, text}] for package warnings Plume knows (signed requests, no default environment) |
| `search_docs` | `api, query, kind?, top_k?, version?` | hybrid (vector + full-text, weighted RRF: with a real embedding model k 10 and the vector ranking weighted 5:1, see `PLUME_SEARCH_RRF_K`/`PLUME_SEARCH_DENSE_WEIGHT`) hits, one per document; a knowledge-export page in the top results keeps one of its endpoints right after it (pages are never demoted); at least two endpoints of the pool stay in the top results |
| `get_document` | `api, doc_id, version?` | full text, fields, source URL, anchor, citation |
| `find_fact` | `api, name, kind?, owner?, resource?, location?, version?` | exact matches with evidence, or `found:false` with `checked`, `complete`, `text_mentions` and the wording to use |
| `check_call` | `api, method, path, params?, version?` | `documented` / `not_documented`, matched endpoint, per-param location |
| `list_builds` | `api` | builds (newest first) with tags |
| `diff_builds` | `api, from_version, to_version?, limit?` | added / changed / removed chunk ids |
| `list_auth_schemes` / `get_auth_scheme` | `api[, scheme_id], version?` | auth schemes as the package states them; detail = the auth JSON + variables schema verbatim; the list carries auth `notices` |
| `list_triggers` / `get_trigger` | `api[, key], version?` | trigger events / webhook topics; `present: false` when the package has none. `get_trigger` adds `payload`: the event's payload schema fields (like a model's), schema and sample, or the connector `model` its ref names; null when the event has no refs |
| `get_environments` | `api, version?` | environments, base URLs, versioning and the variables schema, verbatim, plus environment `notices` |
| `get_vendor_mcp` | `api, version?` | the vendor's own MCP server(s) and tools when the package lists them; `present: false` otherwise |
| `start_set_session` / `get_set_context` / `get_set_session` | `apis, concepts, aliases?` / `set_session` | a model set: pinned builds, one model session per member, relation candidates. **Ask the user about every relation** |
| `submit_model_set` / `get_model_set` / `revise_model_set` | `set_session, draft, based_on?` / `set_id` | the set (members + relations, validated); `get_model_set` renders the view |
| `list_model_sets` / `list_my_model_sets` | `api?` / `owner_keys` | official sets / sets of old owner keys (transition: use `list_my_models(collection)`) |
| `suggest_related` | `apis, concept, limit?, offset?` | related concepts with relation candidates (documented evidence only, cited per API) and the designs it supports; `aliases` for differently named concepts at the same position. The user decides |
| `start_model_session` | `apis, concept` | a session pinned to the current builds (2..6 APIs) |
| `get_model_context` / `get_model_evidence` | `model_session[, api, doc_ids?, cursor?]` | the evidence index; the fields, paged |
| `submit_model_draft` | `model_session, draft, based_on?, collection?` | validated → stored **unlisted** in the user's My models link (`share_url`, `collection {id, url, created}`, `version`) or refused with issue codes |
| `get_model_session` | `model_session` | `open` / `submitted` + `snapshot_id` |
| `revise_model` | `snapshot_id` | a new session on the current builds with the model as `starting_draft` |
| `get_model` | `snapshot_id` | a model (official or unlisted) with `lineage`, `shareUrl`, `revisePrompt` |
| `list_models` | `api?` | official models (latest version of each), newest first |
| `list_my_models` | `collection` (id or URL), or old `owner_keys` | the latest version of each model and set in the user's My models link; with old keys, their models and the links they became |
| `merge_my_models` | `collection, sources` | moves the models and sets of other My models links into this one |

## Maintainer server

`http://127.0.0.1:18481/maintainer/mcp`, `Authorization: Bearer <token>` (401 without; 503 when
no tokens are configured). Tools: `suggest_concepts(apis, q?, only?, require?, limit?,
offset?)` (paged; see canonical-models.md), the model tools above except
`list_my_models` (drafts are stored **unreleased**; `get_model` also shows unreleased models),
`list_models(api?, visibility="all")` (official | unreleased | unlisted | all),
`release_model`, `discard_model`, `generate_model(apis, concept)` (Plume's LLM; returns a job),
`get_generation(job_id)`, `generate_model_set(apis, concepts)` (members by the LLM, relations proposed undecided), `release_model_set` / `discard_model_set`, `publish_build`, `get_job`. See
[canonical-models.md](canonical-models.md).

The same use cases back the HTTP API (`docs/openapi.json`); `POST /v1/apis/{api}/search`
returns the exact MCP payload as `claudePayload`.

Absence rule: say "not documented in build X" only when `find_fact` returns `found:false` and
`complete:true`; with `complete:false` absence is not proven. A schema with more than 2000
fields is listed only to a nesting level; a field not found where such a schema is in scope
gives `complete:false` and the reason "not listed: <doc> schema truncated at nesting level N".

## MCP Apps

Both servers serve `ui://plume/model-view` (`text/html;profile=mcp-app`). `get_model`,
`submit_model_draft` (and on the maintainer server `release_model`, `discard_model`,
`get_generation`) point at it with `_meta.ui.resourceUri`, so Claude web/Desktop show the model
inline; text-only hosts get a summary and the link. Write tools are `visibility: ["model"]`.
See [mcp-apps.md](mcp-apps.md).

**Session parameters** are `model_session` and `set_session`. The old names `session_id` and
`set_session_id` are still accepted. They were renamed because Claude's desktop bridge (through
`mcp-remote`) delivered tool arguments named `session_id` empty. Results carry both keys.
