# Design: model sets, relations between models, and nested objects

Status: **approved** by plume coord on 2026-11-16, with decisions D1–D5 below. It's built in
four cuts, in order.

## Goal (the owner's intent)

- A **model set** groups several canonical models (Product, Variant, Image, Option) with
  **relations** between them, like a DB diagram. The graph's top level shows that diagram.
  Clicking a model opens today's field-mapping view.
- **The user designs each relation.** For example, Variant ↔ Product can be:
  - (a) **embedded**: `Product.variants: Variant[]`;
  - (b) a **reference**: `Variant.product_id → Product.id`.

  The user also picks the cardinality (1:1, 1:n, n:m) and the key fields. In the Claude flow,
  Claude asks and never decides silently. On the web, the choice is editable, and saving makes a
  new version.
- **Nested objects**: a canonical field can be an object or an array of objects with sub-fields
  (`variants[].sku`). Each sub-field is mapped and cited per API, like today's fields.

Plume never invents:
- Relation **candidates** come only from documented evidence, with citations per API.
- Names that differ across APIs are linked only when the docs connect them, and only after the
  user confirms.
- Every model is still validated on its own. A relation is valid only if both ends exist and
  its key fields are documented in the APIs it maps.

## What the packages actually give us (checked on the 1.2 renders)

| Evidence | Shopify | WooCommerce | Mirakl |
|---|---|---|---|
| Nested arrays / objects in a response or model | `variants[].id`, `products[].options[].product_id`, `line_items[].variant_id` | `line_items[].variation_id`, `attributes[].variation` | `orders[].customer.shipping_address.street_2` |
| Sub-resource paths | `GET /products/{product_id}/variants.json`, `/products/{product_id}/images/{image_id}.json` | `GET /products/{product_id}/variations`, `/variations/{id}` | none |
| Id fields whose description names the target | `image.product_id`: "Unique numeric identifier for the associated product." | `parent_id` in `model:refund`: "The ID of the order the refund is associated with." | `products[].product_id`: "Product ID" |

Two consequences:

- **Id-field rule.** The *description* must name the target. WooCommerce's refund `parent_id`
  points to **Order**, which its name doesn't say.
- **Names differ across APIs.** Shopify "variant" and WooCommerce "variation" occupy the same
  structural position (a sub-resource of product). No document says they are the same thing.
  See decision **D2**.

## 1. Data shape

### 1.1 Nested objects inside one model

A canonical field may be `type: "object"` or `type: "array"` with its own `fields`. Sub-fields
have the same shape as today's fields, and nesting goes at most **3 levels** deep.

```json
{"name": "variants", "type": "array", "description": "...", "required": false,
 "sources": {"shopify": {"paths": [{"path": "variants"}], "evidence": [...]}},
 "fields": [
   {"name": "sku", "type": "string",
    "sources": {"shopify": {"paths": [{"path": "variants[].sku"}], "evidence": [...]},
                "woocommerce": {"paths": [{"path": "sku"}], "fetch": "GET /products/{product_id}/variations",
                                "evidence": [...]}}}]}
```

- **Canonical path.** A sub-field's canonical path is derived: `variants[].sku` for arrays,
  `address.city` for objects. The UI, the issues and the coverage counts use it.
- **API paths.** Source `paths` are absolute API paths. A WooCommerce variation's `sku` comes
  from a different endpoint, so it uses `fetch` (and `join`), as today.
- **Validation.** Recursive. Every leaf and container mapping is checked with today's codes;
  `Issue.field` carries the canonical path.
- **Coverage** counts leaves, so containers don't inflate it.
- **Old models** have no `fields` children and are unchanged. The content hash covers children,
  so a nested draft gets a new id.

A nested object **is part of its model**: Order's `shipping_address` has no model of its own.
When the nested thing is a model of the set, it's an **embedded relation** instead (1.3). The
parent field then says `"model": "Variant"` and has no children of its own, because the Variant
model defines them.

### 1.2 Model set

A **model set** is an immutable snapshot:

| Field | Meaning |
|---|---|
| `id`, `lineage {id, version, versions, basedOn}`, `visibility`, `origin`, `generator`, `createdAt`, `releasedAt` | same rules as models (random `u-`/`s-` ids for unlisted, owner keys per lineage, release/discard by maintainers) |
| `name`, `description` | the set ("Catalog") |
| `inputs` | the pinned builds of its 2..6 APIs, shared by every member |
| `members` | `[{concept: "Variant", modelId: "<model snapshot id>"}]`, 1..8 models |
| `relations` | see 1.3 |
| `openQuestions` | as in models; relations the user hasn't decided yet stay here |

**Members are ordinary model snapshots** (validated alone, with their own lineage and link).
A set **pins exact member snapshot ids**, so a set version never changes under you.

- **Changing a model in a set.** Revise the model, which makes a new model version, then save a
  set version that points to it.
- **Pinned builds must agree.** Every member must be pinned to the set's `inputs`. A member on
  older builds makes the set **stale** and must be revised before the next set version.
  Mixing builds isn't allowed.
- **Visibility of members** (rule: a set never exposes more than its members):
  - an **official** set references only official models; releasing a set releases its
    unreleased members in the same step;
  - an **unlisted** set references official or unlisted models;
  - an **unreleased** set references official or unreleased ones.

### 1.3 Relation

The design the user chose, plus how each API represents it, with evidence:

```json
{"id": "product-variants",
 "from": "Product", "to": "Variant",
 "kind": "embedded",                 // embedded | reference
 "cardinality": "1:n",               // 1:1 | 1:n | n:1 | n:m
 "embed": {"field": "variants"},     // embedded: the field of `from` that holds `to`
 "ref":   null,                      // reference: {"field": "product_id" (on `from`), "key": "id" (on `to`)}
 "confirmed": true,                  // the user chose this design (false = proposed, shown as a question)
 "candidate": "c-7f3a…",             // the candidate it came from (or null when drafted from evidence directly)
 "sources": {
   "shopify":     {"as": "nested", "paths": ["variants[]"], "evidence": [...]},
   "woocommerce": {"as": "sub_resource", "fetch": "GET /products/{product_id}/variations",
                   "paths": ["product_id"], "evidence": [...]},
   "mirakl":      null}}             // the API doesn't document the relation (shown as unsupported)
```

- `kind` and `cardinality` are **the canonical design**, chosen by the user.
- `sources[api].as` is **how the API documents it**: `nested`, `sub_resource`, `id_field` or
  `model_ref`. The two may differ. A canonical embedded `Product.variants` can be fed by
  WooCommerce's sub-resource endpoint; the mapping says how.
- **Requirements by kind.** An embedded relation needs `from.<embed.field>` to exist with
  `model: to`; its type is `array` for 1:n or n:m and `object` for 1:1. A reference needs
  `from.<ref.field>` and `to.<ref.key>` to exist as canonical fields of the member models.
- **n:m.** A reference through a join model (a third member) or an id-array field
  (`variant_ids`); allowed only when one of those is documented.

### 1.4 Relation validation (new codes; the members' own codes are unchanged)

| Code | When |
|---|---|
| `RELATION_END_NOT_FOUND` | `from`/`to` is not a member concept |
| `RELATION_FIELD_NOT_FOUND` | the embed field or the ref/key field is not a canonical field of that member model |
| `RELATION_SHAPE_MISMATCH` | cardinality vs field type (1:n embedded needs an array field `model: to`) |
| `FIELD_NOT_FOUND` / `ENDPOINT_NOT_FOUND` | a relation source path / fetch is not documented in that API (same oracle as fields) |
| `MISSING_CITATION` / `DOC_NOT_FOUND` / `QUOTE_NOT_FOUND` | relation evidence, as for fields |
| `API_NOT_IN_SET` | a relation source names an API outside the set |
| `MEMBER_NOT_VISIBLE` / `MEMBER_STALE` | a member the caller can't see, or a member pinned to other builds |

Relations with `confirmed: false` are stored but shown as proposals. The text and the view
both say "not decided".

## 2. Relation candidates (evidence only)

`relation_candidates(apis, concepts)` is deterministic, with no LLM. For each pair of concepts
(and each pinned API) it collects:

| Kind (`as`) | Rule | Evidence (cited) | Suggests |
|---|---|---|---|
| `nested` | a model/response document of concept A has a field path `x[]...` or `x....` whose key normalises to concept B | the container field's doc + its description (or the first sub-field's) | embedded A→B, 1:n (`[]`) or 1:1 |
| `sub_resource` | an endpoint path `/{a}/{a_id}/{b}` (literal segments normalising to A and B) | the endpoint doc + its summary line | reference B→A n:1 (or embedded A→B 1:n) |
| `id_field` | a field `<b>_id` / `parent_id` / `<x>_ids` in A's documents whose **description names** B (B's name or plural, word-boundary) | the field's description | reference A→B n:1 (`_ids` → n:m) |
| `model_ref` | model A has a field whose type/schema names model B | the field line | embedded A→B |

- A candidate is `{id, from, to, options: [{kind, cardinality, embed|ref}], sources: {api:
  {as, paths, fetch?, evidence[]}}}`.
- `options` lists only designs the evidence supports, each with **what it needs**. Option (b)
  needs `Variant.product_id` mapped. The UI and Claude offer those options, and the user picks.
- **Names across APIs (rule 2):** concept keys are matched exactly, as today. Different words
  (`variant` vs `variation`) produce an **alias candidate** `{concepts: ["variant",
  "variation"], apis, evidence}` only under the condition in **D2**. Accepting it is a user
  action, recorded in the set (`aliases`), never automatic.

### Suggest related concepts

`POST /v1/models/suggest-related {apis, concept}` lists the concepts that have relation
candidates with the picked one. Each comes with the candidate kinds and per-API evidence
counts, e.g. for Product: Variant (nested + sub_resource in Shopify; sub_resource in
WooCommerce), Image, Option. Same paging and filters style as suggest-v2.

## 3. Evidence pack (Claude and server generation)

- **`start_set_session(apis, concepts[1..8])`** pins the builds once. It creates one model
  session per concept, so the existing tools work per member, plus a **set session** that holds
  them.
- **`get_set_context(set_session)`** returns the bounded index:
  - per concept, the per-API documents as today, capped at 20 per concept per API, or 10 when
    there are more than 3 concepts;
  - the relation candidates with their evidence;
  - the draft format and rules for sets;
  - for each concept, an existing visible model snapshot already pinned to these builds, if
    any, so Claude can reuse it instead of rewriting.
- **Per member**: `get_model_evidence` (paged, ~20k characters per call) and
  `submit_model_draft` on the member's session, as today. Nested fields need no new tool: the
  evidence already lists `x[].y` paths.
- **Relations**: Claude reads the candidates and **asks the user** for every relation it wants
  to include, offering the candidate's options. Then it calls
  `submit_model_set(set_session, {name, description, members: {concept: modelId}, relations,
  open_questions})`. Undecided relations go to `open_questions` (or `confirmed: false`).
  Plume can't verify a conversation took place. The tool text, the skill and the server
  instructions make asking the rule, and the stored set shows each relation as
  confirmed or proposed.
- **Server generation (maintainer, Gemini)** writes the member models with the same loop as
  today and adds relations only as `confirmed: false` proposals. The maintainer decides them
  on the web before release. A set with unconfirmed relations can't be released (409).

## 4. MCP tools and HTTP

**MCP (reader; the maintainer server has the same tools, storing unreleased):**

| Tool | Does |
|---|---|
| `suggest_related(apis, concept)` | concepts related to one concept |
| `start_set_session(apis, concepts)` | pins the builds; returns the member sessions |
| `get_set_context(set_session_id)` | the bounded evidence index and relation candidates |
| `submit_model_set(set_session_id, draft, based_on?)` | validated, then stored; `owner_key` once for a new lineage |
| `get_model_set(id)` | the set (view-bound, `ui://plume/model-view`) |
| `revise_model_set(id)` | a set session on the current builds, the set as the starting draft |
| `list_model_sets(api?)` | official sets |
| `list_my_model_sets(owner_keys)` | the user's own sets |
| `release_model_set` / `discard_model_set` | maintainer only |

**HTTP** mirrors these under `/v1/model-sets`:

- `POST /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/context`, `POST /sessions/{id}/draft`
- `GET` (official) and `GET /{id}`
- `POST /{id}/revise`, `POST /mine`
- `POST /{id}/release` and `POST /{id}/discard` (token)
- `POST /v1/models/suggest-related`
- **Web edit:** `POST /v1/model-sets/{id}/relations {relations, based_on}`. It changes relation
  designs only and makes a new set version: unlisted without the token, unreleased with it.
  It's allowed only between options whose required fields already exist in the member models,
  for example switching to a reference when `Variant.product_id` is mapped. Anything that needs
  a new or changed field goes through Claude (revise the member).

## 5. Storage and migration (0008)

- `model_sets`: `set_id`, `lineage_id`, `version`, `visibility`, `origin`, `generator`,
  `based_on`, `content_key`, `inputs`, `apis[]`, `body` jsonb (members, relations, aliases,
  open questions), `created_at`, `released_at`. Unique `(lineage_id, version)`. The same
  immutable trigger applies; only `visibility` and `released_at` may change.
- `model_set_lineages(lineage_id, owner_key_hash, created_at)` and `model_set_members(set_id,
  concept, snapshot_id)`. The members table answers "which sets use this model" for staleness,
  and for the warning when a member is discarded.
- `model_sessions` gains `set_session_id` (nullable). New table
  `model_set_sessions(id, apis, inputs, concepts[], based_on, origin, created_at)`.
- Nested fields need **no schema change**: they live in the model's `model` jsonb. The parser
  and `draft_json` become recursive.
- Existing models and data are untouched, and no backfill is needed.

## 6. How the web and the widget read it

- `GET /v1/model-sets/{id}` returns:
  - `{kind: "model_set", id, name, visibility, lineage, inputs (with logos), stale}`;
  - `members: [{concept, modelId, name, fieldCount, coverage per API, visibility}]`;
  - `relations: [{id, from, to, kind, cardinality, embed|ref, confirmed, sources per API with
    evidence, support per API}]`;
  - `openQuestions`, `shareUrl`, `revisePrompt`;
  - `editableOptions` per relation: the alternative designs the evidence allows and whether
    each is editable on the web (its required fields exist).
- **Graph top level:**
  - nodes are the members;
  - edges are relations: solid = embedded, dashed = reference, labelled with the cardinality;
  - per-API badges show `nested` / `sub_resource` / `id_field` / unsupported;
  - unconfirmed relations are drawn as proposals.
- Clicking a node opens `GET /v1/models/{modelId}`, today's view. Nested fields show as
  expandable rows (canonical path, per-API paths).
- **MCP App:** the same `ui://plume/model-view` bundle branches on `structuredContent.kind`
  (`model_set` vs a model). The text fallback lists members, relations and the link.

## 7. Plan (each step is a cut with the usual gate)

1. **Nested objects:** parser, validation, coverage, payload, docs. Useful on its own; no set
   needed.
2. **Candidates + suggest-related:** read-only, tested on the real 1.2 renders (Product ↔
   Variant/Variation/Image/Option).
3. **Sets:** migration 0008, set sessions, submit, versions, visibility, owner keys, HTTP + MCP,
   plugin skill (ask the user for every relation).
4. **Web relation edit + MCP App set view + Gemini proposals.** Shapes go to plume-9a after
   step 1 for the nested rows, and after step 3 for the diagram.

## Decisions (approved 2026-11-16)

- D1: sets have 2..6 APIs, like models.
- D2: as proposed. An alias candidate needs structural evidence in **both** APIs, both cited, and
  is only a candidate until the user accepts it. The coordinator may come back if the owner
  wants it stricter.
- D3: releasing a set releases its unreleased members in one step. The release confirmation
  (web and tool result) **lists the members released with it**.
- D4: 1..8 members, nesting depth 3.
- D5: members are shared and referenced; a model can be in several sets.

## Decisions as proposed

- **D1. Can a set have one API?** The owner's rule for models is 2..6. I propose the same for
  sets, so a set always compares APIs.
- **D2. When are differently named concepts connected (rule 2)?** No document says "a
  WooCommerce variation is a Shopify variant". I propose that an alias candidate needs
  **structural evidence in both APIs**: both are a sub-resource (or nested array) of the same,
  exactly matching concept. Shopify `/products/{id}/variants` and WooCommerce
  `/products/{id}/variations` qualify, with both endpoints cited. The user must accept it. If
  the owner wants it stricter (an explicit textual link only), there will be **no** variant ↔
  variation candidate on today's packages.
- **D3. Releasing a set releases its unreleased members.** The alternative is refusing until
  each member is released. I propose doing both in one step.
- **D4. Members per set: 1..8,** and nesting depth 3. The evidence budget grows with members.
- **D5. Can a member model belong to several sets?** I propose yes: models stay independent,
  and sets reference them.
