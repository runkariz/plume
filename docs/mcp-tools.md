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
| `get_model` | `snapshot_id` | a stored canonical model |
| `list_models` | `api?` | stored canonical models, newest first |

## Maintainer server

`http://127.0.0.1:18481/maintainer/mcp`, `Authorization: Bearer <token>` (401 without; 503 when
no tokens are configured). Tools: `suggest_concepts`, `start_model_session`,
`get_model_context`, `submit_model_draft`, `get_model`, `list_models`, `publish_build`,
`get_job`. See [canonical-models.md](canonical-models.md).

The same use cases back the HTTP API (`docs/openapi.json`); `POST /v1/apis/{api}/search`
returns the exact MCP payload as `claudePayload`.

Absence rule: say "not documented in build X" only when `find_fact` returns `found:false` and
`complete:true`; with `complete:false` absence is not proven.
