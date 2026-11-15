---
name: plume
description: Answer questions about a third-party API (endpoints, fields, scopes, limits, whether a call is valid) from Plume's versioned documentation, with citations. Use when the user asks how an API works, whether a field or endpoint exists, or to check a call before writing integration code.
---

# Answering API questions with Plume

Plume holds API documentation as immutable builds (tag `latest` by default). It retrieves;
you write the answer. Every result names its `build` and `docs_as_of`.

1. `list_apis` to find the API id (e.g. `shopify`).
2. `search_docs(api, query)` to find candidates, then `get_document(api, doc_id)` for each one
   you rely on. Quote the relevant lines and cite `source_url`.
3. Existence questions ("is there a field X?", "which scope does Y need?") go to
   `find_fact(api, name)`:
   - `found: true`: answer with the evidence (`owner_id`, `location`, `source_url`).
   - `found: false` and `complete: true`: say "not documented in build <build>". Never say
     "does not exist".
   - `found: false` and `complete: false`: absence is not proven; say so and name the
     incomplete sources.
   - Read `text_mentions` before concluding: the name may appear only in prose.
4. Before writing code that calls the API, `check_call(api, method, path, params)`.
5. When the user cares about a version, pass `version` (a tag or a build id) and say which
   build you used.

Do not invent endpoints, fields or scopes. If Plume has nothing, say what you checked.
