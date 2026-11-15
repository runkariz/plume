# "My models" link (collections)

Owner decision (2026-11-16): replace per-model owner keys with one link per person. No accounts:
**the link is the identity**.

## What a collection is

- `c-` + `secrets.token_urlsafe(16)` (128 random bits). Its page is `/mine/<id>` on the web
  (`<PLUME_WEB_PUBLIC_URL>/mine/<id>` when set, else the path).
- It holds **lineages** of user models and user model sets (kind `model` | `set`). Listing a
  collection shows the latest non-discarded version of each, with its version count, newest
  first. Unlisted models are included: they are already readable by anyone with their link.
- It is a **list**, not an admin key: it grants nothing beyond seeing which models are in it.
  Anyone with a model's link can still add a version to it (as before).
- Cap: `MAX_COLLECTION_ITEMS = 500` lineages. Adding beyond that is refused (400).
- Maintainers do not use collections: maintainer saves stay unreleased/official as today.

## Saving

- A user save (MCP `submit_model_draft` / `submit_model_set`, HTTP session submit, web paste or
  edit) takes an optional `collection`.
  - Omitted → a new collection is created and returned.
  - Known → the new lineage (or the lineage the version belongs to) is added to it.
  - Unknown (mistyped, or from another deployment) → a new one is created; the answer says so
    (`collection.created: true`, `collection.note`).
- A version (`based_on` an unlisted model) made with a collection joins that collection. Its
  lineage may then sit in several collections (whoever saved versions); that is fine.
- Plume never answers with a collection the caller did not send. A version of someone else's
  model (anyone with its link may add one) saved without `collection` gets a NEW link for the
  saver, not the author's. Likewise a retry of the same draft without `collection` returns the
  stored model in a new link (the first answer may never have arrived).
- Answer shape: `collection: {id, url, created, note?}` in structuredContent / HTTP JSON; the
  text says "Your models: <url> — bookmark it to find them later." The MCP instructions tell
  Claude to pass the collection it already got in this conversation on later saves.
- No new owner keys are issued.

## Reading and merging

- `GET /v1/collections/{id}` → `{id, url, models: [ModelListItem], sets: [SetListItem],
  count}`; 404 for an unknown id. MCP `list_my_models(collection)` returns the same.
- `POST /v1/collections/{id}/merge {from: [ids]}` moves every lineage of the `from`
  collections into `{id}` (within the cap) and empties them; the old links then show an empty
  list with `mergedInto: <id>`. MCP `merge_my_models(collection, from)`.

## Transition from owner keys

- Migration 0012 creates `collections` and `collection_items`. Every distinct owner-key hash on
  `model_lineages` and `model_set_lineages` gets one collection (`legacy_key_hash` = that hash),
  holding all lineages with that hash (models and sets of the same key share one collection).
- Old keys keep working for one transition: `list_my_models(owner_keys=[...])` and
  `POST /v1/models/mine` / `/v1/model-sets/mine` still list by key, and now also return
  `collections: [{id, url}]` for the keys' collections so clients can switch to the link.
- The owner-key columns stay (read-only) until the transition ends; nothing writes new hashes.

## Abuse and limits

- Creation happens only on a save, which is rate limited per client like every route.
- The cap bounds one collection; pruning of unlisted models and empty collections stays the
  open gap in `security.md`.

## Web (plume-9a)

- Keep the collection link in `localStorage`; "Your models" on /models shows that collection,
  with "Open another My models link".
- The MCP widget shows the link with Copy instead of the key.
