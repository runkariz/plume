---
name: plume-models
description: Build a canonical data model (e.g. Order, Product) across two or more APIs with Plume, grounded in their documentation, with every mapping cited. Use when asked to unify, map or compare a concept across APIs, or to write integration code that converts between them.
---

# Canonical models with Plume

Needs the `plume-maintainer` MCP server (bearer token). Reading stored models only needs the
reader (`get_model`, `list_models`).

1. Check `list_models(api)` first: reuse a snapshot for the same APIs and concept only when
   `stale` is false. `stale: true` means it was built on older builds (see `stale_inputs`):
   tell the user and regenerate it (steps 2-6) or ask before relying on it.
2. `suggest_concepts(apis)` → pick the concept the user means.
3. `start_model_session(apis, concept)` → `get_model_context(session_id)` (a compact index).
4. For each API, `get_model_evidence(session_id, api)` and follow `next_cursor` until it is
   null (pass `doc_ids` to read other documents of the pinned build).
5. Write the model in the `draft_format`, using only fields returned by the evidence:
   - copy `paths` exactly; cite each mapping with the `doc_id` and a verbatim `quote`;
   - leave an API out of a field when it has no such data (never invent);
   - describe derived values with `transform` / `join`;
   - put unresolved semantics in `open_questions` (do not decide them).
6. `submit_model_draft(session_id, draft)`. On refusal, fix exactly the listed issues
   (`MISSING_CITATION`, `QUOTE_NOT_FOUND`, `FIELD_NOT_FOUND`, `ENDPOINT_NOT_FOUND`,
   `DOC_NOT_FOUND`, `API_NOT_IN_SESSION`) and resubmit.
7. Tell the user the snapshot id, the coverage per API and the open questions. The model is
   "generated, unverified". When writing mapping code, check calls with `check_call`.
