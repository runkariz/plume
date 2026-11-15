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
| `connector/auth/<id>.json` | `id`, `name`, `authorizationType`, `grantType`, `headerName`, `scopes[] {scope, description}` |
| `knowledge-export/**/*.md` (optional) | page text; front matter `source_url`; first `# ` heading is the title |
| `manifest.json` (package root, optional) | `runId` only |

The endpoint document id is `endpoint:METHOD~<path>`, built from `url` with `{{req_vars.x}}` →
`{x}`, the server prefix removed and the version segment replaced by `{version}`. `endpointId`
is kept as `source_id` only, because it changes when the vendor version rolls.

## Ignored

- The root `manifest.json` `schemaVersion` (stream's run manifest; it says 2.0 while
  `connector/package.json` says 1.2). Plume follows `connector/package.json`.
- Stream internals outside `connector/` and `knowledge-export/`: `endpoints/*.md`,
  `*.diagnostic.md`, `_models/`, `_business/`, `_pages/`, `_diagnostics/`, `_report.md`,
  `_index.md`, `_progress/`, `_quality/`, `_specs/`, `_ui/`, `_triggers/`, `_backfill/`.
- In `connector/`: `*.sample.json`, `presets/`, `triggers/`, `environment.variables.*`,
  `icon.*` (the `iconUrl` field is used instead), `dataSourceExtractionCode`, UI hints
  (`x-ui-*`, `colorSetId`), `examples`.

## Hash

The package hash (part of the build id) covers every file under `connector/` and
`knowledge-export/`, so any change there gives a new build.
