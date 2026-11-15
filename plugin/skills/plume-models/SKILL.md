---
name: plume-models
description: Build, save, list and revise a canonical data model (e.g. Order, Product) across two to six APIs with Plume, grounded in their documentation, with every mapping cited. Use when asked to unify, map or compare a concept across APIs, to change a model the user made before, or to write integration code that converts between them.
---

# Canonical models with Plume

Everything here works with the public `plume` MCP server; no token is needed. A model you
submit is stored **unlisted**: anyone with its link can read it, but it is never listed
publicly. Only a maintainer can make a model official.

## Keep the user's models locally

Plume has no accounts. When a submit starts a new model it returns `owner_key` **once**. Save it
right away with the model id in `~/.plume/models.json` (create the file and its folder if
needed; keep the file private, mode 600):

```json
{"models": [{"snapshot_id": "u-…", "owner_key": "pk_…", "concept": "Order",
             "apis": ["shopify", "woocommerce"], "share_url": "…", "saved_at": "2026-11-16"}]}
```

Append to the list; never print the owner keys in the chat. To show the user their models,
read the file and call `list_my_models(owner_keys)`: it returns the latest version of each.

## Make a model

1. Check `list_models(api)` first (official models): reuse one for the same APIs and concept
   only when `stale` is false. `stale: true` means it was built on older builds (see
   `stale_inputs`); say so and make a new one, or ask.
2. `start_model_session(apis, concept)` → `get_model_context(session_id)` (a compact index).
3. For each API, `get_model_evidence(session_id, api)` and follow `next_cursor` until it is
   null (pass `doc_ids` to read other documents of the pinned build).
4. Write the model in the `draft_format`, using only fields returned by the evidence:
   - copy `paths` exactly; cite each mapping with the `doc_id` and a verbatim `quote`;
   - leave an API out of a field when it has no such data (never invent);
   - describe derived values with `transform` / `join`;
   - put unresolved semantics in `open_questions` (do not decide them).
5. `submit_model_draft(session_id, draft)`. On refusal, fix exactly the listed issues
   (`MISSING_CITATION`, `QUOTE_NOT_FOUND`, `FIELD_NOT_FOUND`, `ENDPOINT_NOT_FOUND`,
   `DOC_NOT_FOUND`, `API_NOT_IN_SESSION`, `INVALID_FORMAT`) and resubmit.
6. Save `owner_key` + `snapshot_id` as above. Give the user the `share_url` (or the
   `share_path` on their Plume web UI), the coverage per API and the open questions. The model
   is "generated, unverified". When writing mapping code, check calls with `check_call`.

## Change a model

Models never change in place; a change is a new version.

1. `revise_model(snapshot_id)` opens a session on the APIs' current builds with the model as
   `starting_draft`.
2. Read the evidence you need (`get_model_context`, `get_model_evidence`), apply the user's
   changes to `starting_draft`, keep every citation verbatim.
3. `submit_model_draft(session_id, draft, based_on=snapshot_id)`. The result is the next
   version (`version`, and `lineage` in `get_model`). Update the saved entry's `snapshot_id`
   to the new id (the owner key stays the same).

Revising an official model, or someone else's shared model, creates your own unlisted model
based on it (with a new `owner_key`) when you may not add to theirs; save that key too.

## Maintainers

With the `plume-maintainer` MCP server (bearer token) the same tools store models
**unreleased**. Review them with `list_models(visibility="unreleased")` and `get_model`, then
`release_model(id)` (official, listed) or `discard_model(id)`. `generate_model(apis, concept)`
lets Plume write the model with its own LLM (same validation); poll `get_generation(job_id)`.
