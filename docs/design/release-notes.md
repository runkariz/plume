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
  "from": "b-…", "to": "b-…", "toDocsAsOf": "2026-11-15",
  "wordingOnly": false,
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

- **Quotes** are at most 500 characters, cut at a word boundary with "…".
- **Links**: `sourceUrl` + `anchor` point to the vendor page. For an item in the latest build,
  `subject.docId` opens it in Plume. For a REMOVED item, open `GET
  /v1/apis/{api}/documents/{docId}?version=<from>`: this already reads past builds, since builds
  are kept.
- **`wordingOnly`** is true when `op = description`, and on a build summary when every visible
  item is description-only. Such items are never breaking. The UI collapses them ("wording only:
  12 descriptions changed"), and they don't count toward a badge.
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

Signals per item, from the page(s) the item's document came from (`sourceUrl`). The page
text is stream's source snapshot (`pages.json` → `_sources/<sha>.txt`). The knowledge-export
pages are NOT source text: they are LLM-written and vary between runs (found while building
phase 2), so they never confirm or disprove a change.

- **P (page)**: B's `cleanSha256` (text after stream's page cleaner) differs from A's. A
  change in `contentSha256` alone means only page chrome moved. P is unknown when either side
  lacks a hash, and when A's `pages.json` is a baseline written after its extraction
  (`baselineKind: "snapshot-after-extraction"`, the three frozen 2026-11-15 packages): such a
  baseline only serves the NEXT package.
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
  - Files stream lists as LLM-written (`llmFiles`: rules, gold questions) vary between runs.
    They are recorded and kept out of extraction judgements.
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

## 5. Post-release review (owner decision 2026-11-16: no blocking gate)

A new build is **never held** because of suspect items. Publishing (the `latest` tag) goes
ahead as today, and the existing eval gate stays. Afterwards the maintainer reviews the notes.

- **Review status** per notes: `pending` (new) → `kept` | `rolled_back`. Every decision is
  recorded in `decisions[]` (who, when, decision, note or reason).
- **needsAttention** (bool) with **attentionReason** (one plain line) raises the review's
  priority, never blocks. It is set when any of these holds:
  - any suspect removed endpoint;
  - 5 or more suspect breaking items (`PLUME_NOTES_ATTENTION_SUSPECT_BREAKING`);
  - gold recall dropped by more than `PLUME_GATE_MAX_DROP`;
  - A1 or A3 fired (30% of a document's fields or a model's properties, or 20 or more fields).
- **Keep**: the build stays `latest`; the status becomes `kept`.
- **Roll back** (one click, a reason is required, at most 500 characters): moves `latest` from
  this build back to its base (`from`). The build stays loaded but untagged, and the status
  becomes `rolled_back`.
  - Only the build that is currently `latest` can be rolled back. Otherwise, and for a first
    build (no base), the answer is 409 `invalid_state`.
  - Prod follows through the usual flow (dump, restore, tag); nothing else changes.
- **Roll forward** (undo): keeping a `rolled_back` build moves `latest` to it again, as long as
  `latest` is still its base (409 otherwise). There is no general tag-move endpoint;
  `plume tag` stays the CLI's.
- **Copy issues**: the extraction report as one ready-to-paste text for stream (Markdown or
  plain), built on the server. It contains build ids, `streamVersion` and `rulesHash`, then per
  artifact rule: the subject (unit or page), A/B values, the source URL and the page hashes. It
  is capped at 200 items, followed by "+N more, see the web report".
- **Promote** a suspect or unknown item to `confirmed` by hand, with a quote the server VERIFIES
  against B's source text (or B's document) using the same normalised containment as model
  citations. A failed check is 422 `QUOTE_NOT_VERIFIED`. On success the item records
  `promotedBy` and `promotedAt`. **Demote** undoes a promotion.
- Same-shape renames are never flagged.

## 6. What stream adds to packages (approved by kariz-core-94, 2026-11-16)

Everything new sits outside `connector/`, and `manifest.json` is unchanged.

1. `pages.json`: per page `url` (no query or fragment), `fetchedAt`, `httpStatus` (or
   `status`/`reason`), `contentSha256` (normalised text before cleaning or LLM),
   `cleanSha256` (after stream's page cleaner) and `snapshot` (`_sources/<sha>.txt`). Plus a
   `units` map: for each unit, all its pages with anchors, and `truncated` / `complete` /
   `partialReason`.
2. `changes.json`: `vendorChangelog` (`stream changelog --since`) and a deterministic
   `pageDiff` against the previous package's `pages.json` (only when stream is given
   `--previous`; absent for a first package).
3. `llmFiles`: which files are LLM-written.
4. The three frozen packages get a no-LLM ledger pass into NEW folder copies (`connector/`
   byte-identical) with `baselineKind: "snapshot-after-extraction"`. They are a baseline only,
   with no "confirmed" claims against 2026-11-15. Mirakl lists its spec document as a page.

Plume reads all of these at load (`infrastructure/sources/package_meta.py`). A missing file is
"no evidence", never an error.

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

- **Absent means not available**: a server without notes (an old package, no predecessor, or
  phase 1 for public surfaces) answers `null` or omits the field. It never sends an
  empty-but-present object meaning "nothing happened". The web detects features this way.
- `GET /v1/apis` list items: `docsUpdated: {build, at, confirmed, likely, breaking,
  wordingOnly} | null`. These are visible counts of the latest build's notes, with no per-card
  call. It is null when the build has no notes or no visible non-wording item.
- `GET /v1/apis/{api}/builds`: the timeline (`id, docsAsOf, tag, createdAt, counts {confirmed,
  likely, breaking}`). With the token it adds `suspect, unknown, status`.
- `GET /v1/apis/{api}/changes?build=<id>|since=<date|build>&cursor=&limit=` (default 50,
  max 200): visible items only.
  - Stable order: breaking first, then kind, then subject path, then op.
  - Filters: `breaking=true`, `kind=`, `op=`, `wordingOnly=true|false`, `q=` (subject text).
  - The response carries `totals {confirmed, likely, breaking, wordingOnly, byKind}` for the
    WHOLE selection, ignoring paging and the q filter, so chips show true counts, plus
    `computedAt` of the notes.
  - `since` spans builds (section 9); items carry `from`, `to` and `toDocsAsOf` for grouping.
- **Maintainer** (bearer):
  - `GET /v1/apis/{api}/builds/{build}/release-notes` returns every item, plus:
    - `review` (pending|kept|rolled_back), `needsAttention` and `attentionReason`;
    - `tagged` (whether this build is `latest`), `computedAt` and `decisions[]`;
    - the extraction report: `report: [{rule, title, explanation, items}]`, where
      `explanation` is one plain sentence written by the server; unknown items appear as rule
      `unknown` ("no source evidence");
    - `package` (streamVersion, rulesHash, extractedAt) for A and B, and the gold delta.
  - `POST …/release-notes/keep {note?}`: on a rolled-back build it rolls forward (see
    section 5).
  - `POST …/release-notes/rollback {reason}` → `{tag: "latest", buildId: <from>, previous:
    <to>, review: "rolled_back"}`.
  - Both answer 409 `invalid_state` when not applicable: a first build, a build that is not
    `latest`, or `latest` that moved on.
  - `GET …/release-notes/issues?format=markdown|text` returns the copy-issues text
    (`text/markdown` or `text/plain`, at most 200 items).
  - `POST …/release-notes/items/{itemId}/promote {quote}` → the item, or 422
    `QUOTE_NOT_VERIFIED`. `POST …/items/{itemId}/demote` undoes it.
  - `GET /v1/apis/{api}/builds` (maintainer) carries per build `review`, `needsAttention` and
    counts.
  - A recomputation keeps the decision history and updates `computedAt`.
- **Maintainer MCP**: `review_release_notes(api, build?)` (the summary, report groups and
  attention), `keep_release(api, build, note?)`, `rollback_release(api, build, reason)`,
  `release_issues(api, build)` (the copy-issues text), and `promote_change(api, build, item,
  quote)` / `demote_change(api, build, item)`.
- `GET /v1/apis/{api}/changes.atom`: one Atom entry per build with visible items (title:
  counts and BREAKING; content: plain-text list with links to `sourceUrl`).
- MCP reader `what_changed(api, since)`: the same visible items. The text tells Claude to
  report only these as API changes, quote the evidence, and say "docs updated, no API change"
  when only descriptions changed (phase 3).
- **Model impact** (server-side, since it knows which document fields a mapping cites):
  - `GET /v1/models/{id}/impact` → `{pinned: {api: build}, latest: {api: build}, status:
    current|updated_unaffected|affected|unknown, affected: [{field, api, change: <item>}],
    counts}`. `unknown` means a pinned build or a build in between has no notes: the UI must
    not say "unaffected" then;
  - `impact: {status, affectedCount, breakingCount}` sits on the model JSON AND on the list
    items of `GET /v1/models`, `GET /v1/model-sets` and the My models collection items (no
    per-row call);
  - a set's JSON has `impact: {status, affectedCount, breakingCount, byMember: [{concept,
    status, affectedCount}]}`, where the set status is the worst of its members (unknown <
    current < updated_unaffected < affected for display);
  - the MCP structuredContent carries `impact` plus at most 5 compact rows `{field, api,
    member?, op, breaking, text}` (`text` is one plain line) and `impactUrl`, not full items.
    The widget has no network.

  A mapping is affected when a **visible** item touches a document field or endpoint it cites
  (paths, evidence doc, `fetch`). Suspect items never make a model "affected". This replaces
  the blanket `stale` badge: `stale` stays as data, and the UI leads with `impact.status`.
- Quotes are always from the vendor docs of the build they describe (A for `before`, B for
  `after`). They are plain text: render them as text with a link to `sourceUrl`, never as HTML.

## 8b. Web (plume-9a)

- **Maintainer first (phase 1)**: after a publish, the build shows its review: status,
  `needsAttention` / `attentionReason`, and the extraction report (groups by rule with the
  server's explanation, A/B values, page hashes; unknown items as "no source evidence"). It
  offers Keep (note), Roll back (reason, with a confirm that says the tag moves back to the
  previous build and can be rolled forward while that build is still `latest`), Copy issues
  (the server's text), Promote/Demote with a quote, and the decision history. Suspect and unknown items appear only on a separate maintainer route
  (`/maintainer/apis/:api/builds/:build/notes`), never mixed into public pages.
- **Public (phase 3)**:
  - API card badge, e.g. "Docs updated 14 Nov: 3 changes, 1 breaking" (text and icon, never
    colour alone). Shown when confirmed + likely non-wording > 0; links to the Changes tab.
  - "Changes" tab on the API page: a build timeline (newest first, tag chips, counts, a BREAKING
    chip when any visible item is breaking). A build opens its list:
    - filter chips: All, Breaking, Endpoints, Fields, Auth, Wording only;
    - items grouped by document, each with an op chip, before → after, the quote as plain text
      and a "Vendor page" link;
    - "per the vendor's changelog" on likely items, and "Subscribe (Atom)";
    - an empty build reads "No API changes found".
  - Model and set pages: an impact banner leads instead of the stale badge.
    - affected: "N mappings affected (M breaking)", with rows linked to the mapping and
      Regenerate for maintainers;
    - updated_unaffected: "Docs updated, your mappings are unaffected";
    - current: quiet;
    - unknown: "Not checked against newer docs".

    Lists show the same chip.
  - Widget: the one-line banner, at most 5 compact rows, and "Open in Plume". No fetch.
- Quotes render as text nodes, chips carry text, lists are paged (100), filters live in the URL,
  and the layout works at 375 px.
- **Reclassification**: deep links to a vanished item show "no longer listed", and
  `computedAt` shows "recomputed hh:mm".
- **Feature detection**: the Changes tab appears when `GET …/builds` has a build with notes;
  the badge when `docsUpdated` is non-null; the impact chip when `impact` exists.

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
2. **Classification with what packages have today**: the artifact rules, quality blockers,
   `failedPages`, `x-complete` flips and flapping. The knowledge-export pages turned out to be
   LLM-written, so with today's packages nothing is `confirmed`: items are `suspect` (an
   artifact fired) or `unknown`. Built 2026-11-16, together with phase 1 and the review.
3. **After stream ships section 6**: P, V and C for every unit. Public surfaces (Changes tab,
   `what_changed`, Atom, `docsUpdated`, impact) are turned on once phase 3 makes
   confirmed/likely meaningful. Before that, users would see almost nothing, which is honest
   but not useful.

## 12. Owner decisions

Decided by the owner (2026-11-16):

1. Thresholds as proposed, used as **needsAttention flags only**: no build is blocked.
2. `likely` is user-visible, labelled "per the vendor's changelog".
3. A maintainer may promote a suspect item to confirmed by hand, with a quote that is verified
   and recorded (and may demote it again).
4. Public surfaces wait for phase 3 (stream's page hashes). Phases 1 and 2 are built now.
