# Release notes: what changed between builds, without inventing

Status: **design, awaiting the owner's approval** (no code yet). Owner decision (2026-11-16):
when a new package for an API is loaded, Plume knows WHAT changed and tells users, never
inventing. Stream is a scraper and has bugs, so every difference is classified by its source
before anyone is told about it.

## 1. What exists today

- `DiffBuilds` / `diff_builds` (MCP) compares two builds by **document content hash**: added,
  changed, removed document ids. It cannot say which field changed or why.
- Each build stores **facts**: endpoints (`METHOD path`), fields (path, location, type,
  required, description, owner document) and scopes. That is the material for a field-level
  diff.
- A package carries:
  - `manifest.json`: `streamVersion`, `rulesHash`, `extractedAt`, `warnings`, and `units[]`
    with `sourceUrl` and `contentHash`. `contentHash` hashes the **extracted unit**, not the
    vendor page, so it changes whether the docs changed or the extractor did.
  - `_quality/report.json` (blockers, warnings) and `_diagnostics/events.jsonl`.
  - Page text only partly: `knowledge-export/pages/*.md` (Shopify: 71 pages) and
    `_pages/*.md` (accessibility snapshots, 5 pages). Most endpoint pages have no stored source
    text.
- Today Plume therefore cannot prove a docs change for most items. Section 6 says what stream
  must add.

## 2. The change item

One record per atomic difference between build A (previous) and build B (new) of one API:

```json
{
  "id": "ch-<hash of api, from, to, kind, subject, path, op>",
  "kind": "endpoint | param | request_field | response_field | model | property | auth_scheme | scope | webhook_event | guide",
  "op": "added | removed | type | required | description | enum | renamed",
  "subject": {"docId": "endpoint:GET~/orders.json", "method": "GET", "path": "/orders.json",
              "model": null, "fieldPath": "line_items[].tax_lines[].rate", "location": "response"},
  "before": {"type": "string", "required": false, "quote": "…"},
  "after":  {"type": "number", "required": false, "quote": "…"},
  "breaking": true,
  "breakingReason": "type changed string -> number",
  "class": "confirmed | likely | suspect | unknown",
  "evidence": {"sourceUrl": "https://…", "anchor": "…", "quote": "verbatim from B's source",
               "pageHashBefore": "…", "pageHashAfter": "…", "changelog": "stream changelog line"},
  "artifactRules": ["A2-alphabetical-cutoff"],
  "visibleToUsers": true
}
```

- **Identity** is stable across recomputation (the id hashes the subject, not the run), so a
  reclassified item keeps its id. Endpoints are keyed by `METHOD path` (with the `@<endpoint
  id>` suffix for collisions). Models are keyed by source title. Fields are keyed by owner,
  location and path.
- **Breaking** is judged per item:
  - removed endpoint, param, field, property, scope or webhook event;
  - a type change (other than widening to a union that includes the old type);
  - a newly required request param or request field;
  - a removed enum value;
  - a removed auth scheme.

  A build is "breaking" when at least one VISIBLE item is breaking. Additions, description
  changes and newly optional fields are never breaking.
- **Renames**: a model or nested type whose property set and types are identical under a new
  name (OrderTaxLine → OrderTaxLines) is one `renamed` item, `visibleToUsers: false`, and no
  change for users. Fields citing it are not reported as removed and added.

## 3. Computing the diff (at load, against the previous build)

1. **Base**: the build the API's `latest` tag pointed to before this load. If there is none, B
   is the first build and has no notes. A yanked or superseded build is never a base. When a
   tag moves back, no notes are recomputed: notes always belong to a (from, to) pair and stay
   stored.
2. Load the facts and documents of A and B. Match endpoints, then fields per owner, then models
   and properties (by source title), auth schemes and scopes, webhook events (trigger
   documents), and guides (by source URL). Emit one item per difference.
3. Descriptions: report a change only when the normalised text differs. Whitespace, case,
   backticks and Markdown don't count, using the same normalisation as model citations.
4. Classify every item (section 4), apply the gate (section 5), and store.
5. **Gold-score delta**: the eval gate already measures recall@k and MRR. The notes carry
   before and after values for both, plus the per-question flips (lost or gained hits), as a
   build-level fact.

## 4. Classification: did the docs change, or did the extraction change?

Signals per item, from the page(s) the item's document came from (`sourceUrl`):

- **P (page)**: B's source page hash differs from A's. It is unknown when either side lacks a
  hash.
- **V (verbatim)**: the new value is in B's source text, using the same normalised containment
  as `QUOTE_NOT_FOUND`.
  - additions: field name plus description;
  - removals: present in A's text and absent from B's;
  - type changes: field name with the new type within one sentence or table row;
  - description changes: the new description.
- **C (changelog)**: stream's changelog for this package, `stream changelog --since
  <A.extractedAt>`, names the page or unit as changed.
- **Artifact rules** (any one marks the item as an extraction suspect):
  - A1 mass removal: more than 30% of a document's fields (or 20 or more) removed while its
    page is unchanged or of unknown change;
  - A2 alphabetical cut-off: the removed fields of a document are exactly a suffix of its
    sorted field names (Order truncated after "l");
  - A3 property-count drop: a model lost more than 30% of its properties while its page is
    unchanged or of unknown change (ProductVariant down to 12);
  - A4 same-shape rename: see renames above;
  - A5 an `x-complete` flip, or a stream quality blocker or warning on the unit;
  - A6 the unit's page is in `failedPages` or `_diagnostics` reports it unread or timed out;
  - A7 flapping: the item undoes a change from the build before (present, absent, present
    again);
  - A8 extractor change: `streamVersion` or `rulesHash` differs between A and B. This alone
    doesn't make an item suspect; it lowers "unknown" items with any other artifact signal to
    suspect, and it is shown in the maintainer report.

Decision, in order:

| Condition | Class |
|---|---|
| P changed **and** V holds, no artifact rule | **confirmed** |
| P changed **and** V holds, artifact rule fires | **confirmed**, artifact noted for the maintainer (the source proves it) |
| P **unchanged** (hashes equal) | **suspect** (the source didn't change, so the extraction did) |
| any of A1–A7 fires and V does not hold | **suspect** |
| C names the page/unit, V not possible | **likely** |
| none of the above | **unknown** |

- **Users** (public API, web, MCP, feed) see only `confirmed` and `likely`. Public counts
  include only those, so nothing tells the public that an extraction misfired.
- **Maintainers** see everything. Suspect items make up the **extraction report** for the
  build. It goes to the maintainer review and, as a bug report (subject, A and B values, page
  hash, rule), to stream.
- **Reclassification**: notes are recomputed when stream delivers what was missing (a page hash,
  a changelog) or a maintainer marks an item. Items keep their ids. Clients must tolerate an
  item changing class or disappearing (a suspect cleared by a re-extraction).
- `unknown` items are listed for maintainers with "no source evidence". After stream's additions
  (section 6) they should be rare.

## 5. The gate

At load the notes get a status:

- `clear`: no suspect breaking items, and gold recall did not drop beyond `PLUME_GATE_MAX_DROP`.
- `review`: suspect breaking items exist. Publishing (the `latest` tag in the maintainer job,
  `plume tag latest` locally) is **blocked** until a maintainer decides:
  - **accept**: publish; suspect items stay hidden, and the decision (who, when, note) is
    stored;
  - **reject**: don't publish; the build stays loaded but untagged, and the extraction report
    goes to stream.

  Threshold: any suspect removed endpoint, or 5 or more suspect breaking items
  (`PLUME_NOTES_SUSPECT_BREAKING_MAX`, default 5).
- Same-shape renames never block.
- The existing eval gate stays as it is. The notes add the extraction check next to it.

## 6. What stream must add to packages (to take to stream via kariz-core-94)

Without these, most items stay `unknown` or rest on artifact rules alone:

1. `pages.json`: one entry per vendor page read:
   - `{url, fetchedAt, httpStatus, contentSha256, snapshot, units: [unit ids]}`;
   - `contentSha256` hashes the **normalised source text** (main content, whitespace
     collapsed), computed before any LLM or extraction step;
   - `snapshot` is a path to that text inside the package (`_sources/<sha>.txt`), or a stable
     snapshot id in stream's archive.

   This gives P and V for every unit, not only the 71 knowledge-export pages.
2. `changes.json`: the output of `stream changelog --since <previous package's extractedAt>` for
   this API, in the package. The previous `runId` and `extractedAt` are named in it.
3. Unit to page mapping for every unit: all pages a unit used, with anchors, not only one
   `sourceUrl`.
4. Per-unit extraction flags:
   - `truncated` (an output limit was hit), `complete` (as `x-complete`) and `partialReason`;
   - the reading order stays deterministic, so two runs on unchanged pages give the same
     output.
5. Keep `streamVersion`, `rulesHash` and `runId` in the manifest (already there).
   `failedPages` and the diagnostics also stay.

## 7. Storage, dumps, prod

- Table `release_notes`:
  - `(api_id, from_build, to_build)` as key; `computed_at`;
  - `status` (clear, review, accepted, rejected) and the `decision` (who, when, note);
  - `summary` (counts per class, visible counts, breaking counts, gold delta).
- Table `release_note_items`: the items of section 2, indexed by `to_build`.
- The **dump** of build B carries its notes (from A) and items, with a version bump of the dump
  format. Restore writes them as they are, so prod shows the same notes even though it never
  computed them.
- The archive manifest (`gs://…/manifests/`) gets the summary: counts, gate status, decision.
- Notes are never recomputed on prod. A reclassification is a new local computation, followed
  by a new dump and a restore of the notes. The build itself is unchanged.

## 8. Surfaces

All reads; suspect and unknown items need the maintainer token.

- `GET /v1/apis` list items: `docsUpdated: {build, at, confirmed, likely, breaking} | null`.
  These are visible counts of the latest build's notes, with no per-card call.
- `GET /v1/apis/{api}/builds`: the timeline (`id, docsAsOf, tag, createdAt, counts {confirmed,
  likely, breaking}`). With the token it adds `suspect, unknown, status`.
- `GET /v1/apis/{api}/changes?build=<id>|since=<date|build>&cursor=`: paged items, visible
  only. `since` spans builds (section 9).
- `GET /v1/apis/{api}/builds/{build}/release-notes` (maintainer): everything, plus the
  extraction report and gate status. `POST …/decision {accept|reject, note}`.
- `GET /v1/apis/{api}/changes.atom`: one Atom entry per build with visible items (title:
  counts and BREAKING; content: plain-text list with links to `sourceUrl`).
- MCP reader `what_changed(api, since)`: the same visible items. The text tells Claude to
  report only these as API changes, quote the evidence, and say "docs updated, no API change"
  when only descriptions changed. MCP maintainer: `review_release_notes(api, build)` and
  `decide_release(api, build, accept|reject, note)`.
- **Model impact** (server-side, since it knows which document fields a mapping cites):
  - `GET /v1/models/{id}/impact` → `{pinned: {api: build}, latest: {api: build}, status:
    current|updated_unaffected|affected, affected: [{field, api, change: <item>}], counts}`;
  - the model JSON carries `impact: {status, affectedCount}`, and the MCP structuredContent
    carries the summary plus at most 5 affected rows (the widget has no network);
  - a set sums its members, naming the member.

  A mapping is affected when a **visible** item touches a document field or endpoint it cites
  (paths, evidence doc, `fetch`). Suspect items never make a model "affected". This replaces
  the blanket `stale` badge: `stale` stays as data, and the UI leads with `impact.status`.
- Quotes are always from the vendor docs of the build they describe (A for `before`, B for
  `after`). They are plain text: render them as text with a link to `sourceUrl`, never as HTML.

## 9. Diffing across several builds (a model pinned three builds back)

Impact and `since=` use the **composition** of the stored per-build notes, not a direct diff of
pinned → latest. That way a field removed and re-added in between shows both items, a suspect
in between stays out, and every item keeps its evidence. A direct diff would hide flapping and
lose the per-build classification. The UI shows the chain per build, and the impact status
counts an item once (net effect per subject).

## 10. Process

local load → notes computed and gated → maintainer review (web or maintainer MCP: accept /
reject, extraction report to stream) → regenerate affected official models
(`impact.status = affected`) → `plume export` (dump with notes) + manifest → archive →
prod `plume restore` (notes restored) → `plume tag latest` on prod.

## 11. Phases

1. **Field-level diff and storage**: items, breaking rules, same-shape renames, gold delta,
   dump and restore, maintainer view. Everything `unknown` except the artifact-rule suspects,
   which already catch Order a–l, ProductVariant and the renames.
2. **Classification with what packages have today**: P and V for the knowledge-export pages,
   the quality report, `failedPages`, diagnostics.
3. **After stream ships section 6**: P, V and C for every unit. Public surfaces (Changes tab,
   `what_changed`, Atom, `docsUpdated`, impact) are turned on once phase 3 makes
   confirmed/likely meaningful. Before that, users would see almost nothing, which is honest
   but not useful.

## 12. Open questions for the owner

1. Thresholds: A1/A3 at 30% (or 20 fields), and the gate at 5 suspect breaking items or any
   suspect removed endpoint.
2. Should `likely` (changelog only, no verbatim proof) be visible to users, labelled "per the
   vendor's changelog"? Proposed: yes.
3. Should a maintainer be able to promote a suspect item to confirmed by hand (with a quote)?
   Proposed: yes, recorded in the decision.
4. Should public surfaces wait for phase 3? Proposed: yes.
