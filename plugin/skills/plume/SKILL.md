---
name: plume
description: Use for ANY question about how a third-party API works when Plume indexes that API (e.g. Shopify, WooCommerce, Mirakl; call list_apis to see all): endpoints, how to create/update/list something, fields, parameters, scopes, limits, errors, whether something exists, or checking a call before writing integration code. Answer only from Plume's documentation, with citations.
---

# Answering API questions with Plume

Plume holds API documentation as immutable builds (tag `latest` by default). It retrieves;
you write the answer, **only from what Plume returns**.

1. If you are not sure the API is indexed, `list_apis`. If it is, do not answer from memory.
2. `search_docs(api, query)` first; then `get_document(api, doc_id)` for each document you rely
   on. Quote the relevant lines and cite `source_url`.
3. Every endpoint, field, parameter, scope or limit you name must come from a Plume result in
   this conversation. No general-knowledge paragraphs or asides, not even labelled ones. If
   Plume does not cover something, say it is not covered.
4. Existence questions ("is there a field X?", "which scope does Y need?") go to
   `find_fact(api, name)`:
   - `found: true`: answer with the evidence (`owner_id`, `location`, `source_url`).
   - `found: false` and `complete: true`: "not documented in build <build>". Never "does not
     exist".
   - `found: false` and `complete: false`: absence is not proven; give the
     `incomplete_reasons`.
   - Read `text_mentions` before concluding: the name may appear only in prose.
5. Before writing code that calls the API, `check_call(api, method, path, params)`.
6. When the user cares about a version, pass `version` (a tag or a build id) and say which
   build you used.
