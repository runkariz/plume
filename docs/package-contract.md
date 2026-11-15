# Input package contract

Plume reads a **connector package**: a directory that contains `connector/` (or is it), with
`connector/package.json` `schemaVersion` **1.x**. Any other major version is refused. The reader
is producer-agnostic: it uses only the files below.

`tests/contract/test_package_contract.py` pins these fields. Point it at a new package before
using it: `PLUME_CONTRACT_PACKAGES=/path/to/pkg uv run pytest tests/contract/test_package_contract.py`.

## Read

| File | Fields used |
|---|---|
| `connector/package.json` | `schemaVersion` (major must be 1) |
| `connector/app.json` | `name` (required; slugged to the API id), `summary`/`description`, `docLink`, `iconUrl`, `category {key, reason, confidence, bundleVersion}`, `apiVersioning.versions`, `baseUrls`, `errorFormat {notes, statusCodes[]}` |
| `connector/endpoints/<id>/request.json` | required: `method`, `url`, `name`, `endpointId`. Optional: `description`, `summary`, `resource`, `operationKind`, `sideEffects`, `isDeprecated`, `deprecation`, `permissionNote`, `requiredScopes[].scopes`, `errors[]`, `pagination`, `businessRules[]`, `responses[] {statusCode, contentType, contentContractRef}`, `provenance {sourceUrl, docAnchor}`, `docLink`, and the `*ContractRef` files below |
| `params.schema.json`, `variables.schema.json`, `headers.schema.json`, `body.schema.json`, `responses/2xx.schema.json` | JSON-schema `properties`, `required`, `items`, `type`, `description`, flattened to dotted names (`a[].b`), depth ≤ 6 |
| `connector/models/<name>.schema.json` | `title`, `description`, `properties` (as above), `x-complete` (false = partial: absence is not proven), `x-source-url` |
| `connector/knowledge/<id>.json` + `<id>.md` | `id`, `title`, `sourceUrl`; the markdown is the guide text |
| `connector/auth/<id>.json` (+ `<id>.variables.schema.json` via `variableContractRef`) | the whole file and its variables schema, verbatim (`GET /v1/apis/{api}/auth[/{id}]`); read for display: `authorizationType`, `grantType`, `headerName`, `codeQueryParamName`, `scopes[]`, `setupSteps`, `tokenLifetime`, `testUrl` |
| `connector/triggers/events/*.json` (optional) | each event verbatim (`key`, `title`, `description`, `resource`, `delivery`, `provenance`) → `GET /v1/apis/{api}/triggers[/{key}]`; no folder = "not in this package" |
| `connector/icon.(png\|svg\|jpg\|webp)`, else `_icon/icon.*` | the package's own icon, stored with the build and served at `GET /v1/apis/{api}/icon` (never a remote URL) |
| `connector/triggers/webhooks/*.json` (optional, 1.2) | the delivery mechanism verbatim (`mode`, `eventsAvailable`, `subscribe`/`unsubscribe`/`list` endpoints, `handshake`, `verification`) → `webhooks` in `GET /v1/apis/{api}/triggers` |
| `connector/mcp/servers/<id>.json` + `mcp/tools/<server>/<tool>/{tool,input.schema,output.schema}.json` (optional, 1.2; only when the vendor runs an MCP server) | verbatim → `GET /v1/apis/{api}/mcp`; absent for docs-only APIs |
| `connector/environment.variables.schema.json` (optional) | verbatim, with `app.json` `environments` and `apiVersioning` → `GET /v1/apis/{api}/environments` |
| `knowledge-export/` v1 (optional; `index.json` `schema: plume.knowledge-export.v1`) | `index.json` `pages[].file`, `complete`; `pages/*.md` front matter `source` and `items[] {id, anchor}` + the page text; `rules.json` `rules[] {id, scope (endpoint id or "resource"), type, text, quote, anchor, sourceUrl, confidence}`; `gold-questions.json` (for `plume gold-import`) |
| `knowledge-export/**/*.md` (optional, without `index.json`) | page text; front matter `source_url`; first `# ` heading is the title |
| `manifest.json` (package root, optional) | `runId` only |

With a v1 knowledge export, each endpoint document gets the section of its page that its
anchor points at (code examples and JSON payloads stripped) and the rules scoped to it, each
with its verified quote; each page's remaining text (intro, property tables, capped at 6,000
characters) and its resource-level rules become one guide (`guide:page-<url>`). A page that
cannot be cut into its endpoints' sections (fewer than half located) keeps only its rules and an
endpoint index, so its full text does not duplicate and outrank the endpoints. The API's display name is
`app.json` `name`, or, when that is an all-lowercase id, the spelling the package's own
summary uses (`woocommerce` → "WooCommerce").

The endpoint document id is `endpoint:METHOD~<path>`, built from `url` with `{{req_vars.x}}` →
`{x}`, the server prefix removed and the version segment replaced by `{version}`. `endpointId`
is kept as `source_id` only, because it changes when the vendor version rolls.

Schema 1.1 and 1.2 both load (major version 1). In 1.2 the producer's `endpointId` carries the API
version; Plume's document ids are built from the method and the version-stripped path, so they do
not change between a 1.1 and a 1.2 render of the same API (checked on Shopify: 292 of 292 endpoint
ids identical).

**`$ref` in schemas.** Model and endpoint schemas may reference sibling schema files in the same
folder (`"items": {"$ref": "orderlineitem.schema.json"}`) and their own `#/$defs/...`. Plume
follows both, with bounded depth and a cycle guard, so a model exposes its item models' fields
(`line_items[].sku`) with their descriptions. Each field's pointer names the file it came from
(`orderlineitem.schema.json#/properties/sku`). Files outside the folder are not read.

**Unresolved include tags.** Markdoc `{% partial … %}`, Liquid `{% include … %}`, Hugo
`{{< include … >}}` and MDX `<Snippet … />` left in a page mean the included content is missing.
Plume flags them at load:
- a warning naming the tags;
- the document is marked incomplete, so absence isn't proven;
- a visible note opens the text.

Expanding them is the producer's job.

## Ignored

- The root `manifest.json` `schemaVersion` (stream's run manifest; it says 2.0 while
  `connector/package.json` says 1.2). Plume follows `connector/package.json`.
- Stream internals outside `connector/` and `knowledge-export/`: `endpoints/*.md`,
  `*.diagnostic.md`, `_models/`, `_business/`, `_pages/`, `_diagnostics/`, `_report.md`,
  `_index.md`, `_progress/`, `_quality/`, `_specs/`, `_ui/`, `_triggers/`, `_backfill/`.
- In `connector/`: `*.sample.json`, `presets/` and `iconUrl` (the package's own icon file is used
  instead). Everything else of an endpoint, model, auth scheme and trigger is kept verbatim as
  the document's `raw` (shown by `GET /v1/apis/{api}/documents/{id}`; over 256 KB it is withheld
  and `rawTruncated` is true), with `request.json` `tags[].name` as the document's `tags`.
- `_triggers/docs-answer.json` (stream's intermediate file); `connector/triggers/events/` is read.

## Hash

The package hash (part of the build id) covers every file under `connector/` and
`knowledge-export/`, so any change there gives a new build.
