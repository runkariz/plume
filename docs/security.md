# Security notes

Self-review of the public surface (2026-11-15). Plume is meant to run as a **public read-only
reader** plus an **authenticated maintainer** part. Findings marked *fixed* were changed in
this review and have tests in `tests/unit/interfaces/test_hardening.py`.

## Surface

| Surface | Auth | Writes |
|---|---|---|
| HTTP reader `/v1/apis/**`, `/health`, `/docs`, `/openapi.json` | none | none |
| HTTP models: `candidates`, `suggest`, `generate` (engine claude), `sessions/**`, `GET /v1/models`, `GET /v1/models/{id}`, `revise`, `mine` | none | sessions; `draft` stores an **unlisted** snapshot (validated) |
| HTTP models: `generate` (engine server), `release`, `discard`, `jobs/**`, unreleased lists and models | bearer | jobs, unreleased snapshots, visibility |
| HTTP maintainer `/v1/maintainer/me`, `/v1/packages`, `/v1/jobs/**` | bearer | jobs, builds, tags |
| MCP reader `/mcp` | none | model sessions and unlisted snapshots only |
| MCP maintainer `/maintainer/mcp` | bearer | sessions, snapshots, tags |
| CLI (`plume load/tag/export/restore/migrate`) | database access | everything |

## Controls

- **Authentication**: maintainer bearer tokens from `PLUME_MAINTAINER_TOKENS` (JSON list,
  `SecretStr`), compared with `hmac.compare_digest`, never logged or rendered (`repr` shows
  `**********`). No tokens configured → maintainer routes answer 503. *Fixed*: tokens shorter
  than 16 characters or with surrounding spaces are refused at startup.
- **Rate limits**: per client address, sliding minute window
  (`PLUME_READER_RATE_LIMIT_PER_MINUTE`, default 120) on every HTTP route except `/health`.
  *Fixed*: the MCP endpoints (reader and maintainer) are rate limited the same way (they had
  none). The limiter keys on the TCP peer by default (`PLUME_TRUSTED_PROXY_HOPS=0`): behind a
  proxy every client then appears as one address and the limit becomes global. Behind N
  trusted proxies set `PLUME_TRUSTED_PROXY_HOPS=N`: the client is the Nth
  `X-Forwarded-For` entry from the right (Werkzeug ProxyFix `x_for=N`); fewer than N entries
  fall back to the peer. Example (GKE): Traefik REPLACES any client `X-Forwarded-For` with the
  remote address, nginx appends Traefik's pod IP, so Plume receives `X-Forwarded-For: client,
  traefik` with nginx as the peer: `PLUME_TRUSTED_PROXY_HOPS=2` counts `client`. Only set it
  behind proxies that overwrite or append the header; otherwise any client can pick the
  address it is counted under. `GET /health` on the API and on the MCP process is exempt (for
  probes; no auth, no database call).
- **Body size**: *fixed*: requests that declare a body over 1 MiB (over
  `PLUME_MAX_UPLOAD_BYTES`, default 200 MiB, for `POST /v1/packages`) are refused with 413
  before the body is read; previously an upload was spooled in full before the size check.
  Request schemas cap query (2000 chars), names (300), params (100) and `top_k` (50).
- **Uploads**: only `.zip`; at most 20,000 files, 1 GiB expanded, expansion ratio 200;
  absolute paths, `..` and symlinks refused; extraction under `<data_dir>/jobs/<job id>/`.
  *Fixed*: the client's filename is stored as `upload.zip` (it was joined into a path; `..` or an
  empty name caused a 500). The original name is only echoed back as data.
- **Error bodies**: application errors return `{error, message, detail}` with a stable code;
  validation errors are FastAPI's 422; anything unexpected is a bare `500 Internal Server
  Error` with no traceback. *Fixed*: a failed maintainer build stored `str(exception)` in the job
  (visible to maintainers), which for database errors can include SQL and parameters; now only
  application errors are shown and other failures say `internal error (<type>); see the server
  log`. Embedding errors include at most 300 characters of the provider's response, never the
  key (it travels in a header, not the URL).
- **CORS**: explicit origins (`PLUME_CORS_ORIGINS`, default the web dev server on 18473),
  methods GET/POST, headers Authorization/Content-Type/Last-Event-ID/Accept, no credentials
  (cookies are not used).
- **MCP CORS**: none by default. `PLUME_MCP_CORS_ORIGINS` opts in explicit origins for
  browser-based MCP clients (testing with the ext-apps basic-host); never `*`.
- **MCP host check**: DNS-rebinding protection on both MCP endpoints with
  `PLUME_MCP_ALLOWED_HOSTS` (default loopback names); a foreign `Host` is refused (tested in
  e2e).
- **Headers**: *fixed*: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site` on every HTTP
  response.
- **SQL**: every query is parameterised; the only interpolated fragments are constants and one
  `int()`-cast setting. `LIKE` patterns escape `%`, `_` and `\`. Full-text input goes through
  `plainto_tsquery`.
- **Integrity**: sealed builds are immutable (domain + storage refuse changes); model snapshots
  are insert-only and a database trigger refuses any `UPDATE` other than `visibility` /
  `released_at` (release, discard); a change to a model is a new version; dumps are verified (chunk hashes →
  sealed content hash, dims, facts) before a restore writes anything, in one transaction.
  Restore is CLI-only.
- **Untrusted text**: document text, titles, quotes and package file names come from third-party
  docs or uploads. Clients must render them as text (the web UI does; MCP clients receive
  JSON). Model drafts are parsed into typed values and every citation is re-checked.
- **Model access**: an unlisted model's id is its share link: `u-` + 128 random bits from
  `secrets`, so ids cannot be guessed or derived from content. Unreleased and discarded models
  answer 404 without the token (existence is not revealed). A user's "My models" link
  (collection, `c-` + 128 random bits) lists their models and sets; it grants nothing else
  (each model is readable by its own link anyway) and holds at most 500. Old owner keys
  (`pk_`, stored only as SHA-256) still find their collection during the transition.
  *Fixed* (found before release, never deployed): a save without `collection` answered with
  the lineage's existing collection, so anyone adding a version to a shared model received the
  author's link and their whole list. Rule now: Plume never answers with a collection the
  caller did not send; without `collection` every save (a version of someone else's model or
  set, a relation edit, a retry) gets a new link. The web client also adopts a returned link
  only if the save created it or the browser sent it. A link lists the version saved into it,
  not a later one someone else added (`newerVersion` points to that). Only a maintainer can make a model official; a user revising an official model gets
  their own unlisted copy. Drafts are capped at 1,000,000 characters.
- **Vertex without a key**: with `PLUME_VERTEX_AUTH=adc` (or `auto` with no key and
  `PLUME_VERTEX_PROJECT` set) embeddings and generation use Application Default Credentials
  (Workload Identity on GKE): a Bearer token refreshed 5 minutes before expiry, sent only in
  the `Authorization` header, never logged; errors name only the exception type. Grant the
  workload's service account `roles/aiplatform.user`, nothing more.
- **Outbound hosts** (egress allowlist; HTTPS 443 only, nothing else is called):

  | Mode | Embeddings | Generation |
  |---|---|---|
  | key, no `PLUME_VERTEX_PROJECT` | `aiplatform.googleapis.com` (express URL) | `aiplatform.googleapis.com` (express URL) |
  | key + project | `{EMBED_LOCATION}-aiplatform.googleapis.com` (`aiplatform.googleapis.com` for `global`) | `{VERTEX_LOCATION}-aiplatform.googleapis.com` (`aiplatform.googleapis.com` for `global`) |
  | ADC (+ project) | as key + project | as key + project; plus `oauth2.googleapis.com` / the GKE metadata server (`169.254.169.254`) for tokens |
  | `PLUME_EMBEDDER=gemini` | `generativelanguage.googleapis.com` | – |
  | `PLUME_EMBEDDER=hash` | none | – |

  Example (EU): key + project, `PLUME_VERTEX_EMBED_LOCATION=europe-west3` →
  `europe-west3-aiplatform.googleapis.com` for embeddings; generation with `gemini-4-argon`
  needs `PLUME_VERTEX_LOCATION=global` → `aiplatform.googleapis.com`.
- **LLM key**: server-side generation reads the Vertex key from `PLUME_VERTEX_KEY_FILE` on each
  call and sends it only in the `x-goog-api-key` header; errors carry the HTTP status, never the
  key or the provider's body. Without a readable key file generation answers 503.
- **Web UI session** (`web/src/app/authStore.ts`): the maintainer token is typed at sign-in and kept in
  `sessionStorage`, so a refresh or a new page in the same tab does not sign the person out; it is gone when the
  tab or browser closes, on **Sign out**, and when the API answers 401 to it (the person returns to sign-in with a
  message). It is never put in a URL, in `localStorage` or in a log, and with storage blocked it lives in memory
  only. The trade-off: a script injected into the page (XSS) could read `sessionStorage`; the UI renders all
  package text as text and the app loads nothing from third parties, which keeps that risk small, but it is not
  zero. A public deployment should move to an `httpOnly`, `SameSite` session cookie set by the API (follow-up,
  not done). The models page also keeps the My models link (list-only, see Model access) in `localStorage`.
- **Secrets**: keys and tokens come only from the environment (`settings.py` is the only env
  reader, enforced by a test). In Docker they are visible to anyone who can run
  `docker inspect`; for anything beyond local use, pass them through a secrets mechanism.
  `.env` files are git-ignored.

## Known gaps (not fixed)

- `POST /v1/models/generate`, `suggest` and draft submission are public and do database work;
  they are rate limited, but sessions and unlisted snapshots are never pruned, so an abuser can
  fill storage at the rate limit (each draft at most ~1 MB). Collections are created only by a
  save and never pruned either. Add retention, per-client quotas or auth for submissions if
  abused.
- Anyone holding an unlisted model's link can add a version to it (by design: "anyone with the
  link"); the owner cannot lock a model.
- The web UI keeps the maintainer token in `sessionStorage` (see Web UI session): an XSS could read it. Move to an
  `httpOnly` session cookie before a public deployment.
- The maintainer API has one role and no per-token audit trail.
- Builds run in-process in the API server (one worker); a slow build occupies it until done.
- No TLS termination: run behind a proxy for anything but localhost.
