"""Release notes: the field-level diff and the docs-vs-extraction classification."""

from dataclasses import replace

from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.knowledge.release_notes import (
    Item,
    PackageMeta,
    attention,
    classify,
    counts,
    diff_documents,
    finish,
    issues_text,
    report,
)

URL = "https://vendor.example/docs/orders"


def _ep(fields: list[FieldSpec], scopes: tuple[str, ...] = ()) -> Document:
    return Document(
        "endpoint:GET~/orders", DocumentKind.ENDPOINT, "List orders", "List orders.",
        source_url=URL, method="GET", path="/orders", fields=tuple(fields), scopes=scopes,
        source_id="get-orders",
    )  # fmt: skip


def _model(title: str, fields: list[FieldSpec]) -> Document:
    return Document(f"model:{title.lower()}", DocumentKind.MODEL, title, title,
                    fields=tuple(fields), source_id=title)  # fmt: skip


def _f(name: str, typ: str = "string", loc: FieldLocation = FieldLocation.RESPONSE,
       required: bool = False, desc: str | None = None) -> FieldSpec:  # fmt: skip
    return FieldSpec(name, loc, typ, required, desc)


def _run(
    old: list[Document],
    new: list[Document],
    meta_a: PackageMeta | None = None,
    meta_b: PackageMeta | None = None,
    previous: list[Item] | None = None,
) -> list[Item]:
    items = diff_documents(old, new)
    classify(items, old, new, meta_a or PackageMeta(), meta_b or PackageMeta(), previous or [])
    return finish(items, "shop", "b-a", "b-b", "2026-11-16")


def _one(items: list[Item], path: str, op: str) -> Item:
    return next(i for i in items if i["subject"]["fieldPath"] == path and i["op"] == op)


def test_field_level_diff_and_breaking() -> None:
    old = [_ep([_f("id"), _f("total", "string"), _f("note", desc="A note."),
                _f("limit", "integer", FieldLocation.QUERY), _f("gone")])]  # fmt: skip
    new = [_ep([_f("id"), _f("total", "number"), _f("note", desc="A longer note."),
                _f("limit", "integer", FieldLocation.QUERY, required=True), _f("added"),
                _f("since", "string", FieldLocation.QUERY, required=True)],
               scopes=("read_orders",))]  # fmt: skip
    items = _run(old, new)
    assert _one(items, "total", "type")["breaking"]
    assert _one(items, "gone", "removed")["breaking"]
    assert _one(items, "limit", "required")["breakingReason"] == "newly required input"
    assert _one(items, "since", "added")["breaking"]  # a new required query param
    assert not _one(items, "added", "added")["breaking"]  # a new response field
    note = _one(items, "note", "description")
    assert (note["breaking"], note["wordingOnly"]) == (False, True)
    scope = next(i for i in items if i["kind"] == "scope")
    assert (scope["op"], scope["breaking"]) == ("added", True)
    assert all(i["id"].startswith("ch-") and i["from"] == "b-a" for i in items)
    assert items[0]["breaking"]  # breaking first


def test_same_shape_rename_is_no_change_for_users() -> None:
    shape = [_f("rate", "number"), _f("title")]
    items = _run([_model("OrderTaxLine", shape)], [_model("OrderTaxLines", shape)])
    assert [(i["op"], i["visibleToUsers"]) for i in items] == [("renamed", False)]
    assert counts(items)["renamed"] == 1
    # a field typed with the renamed model follows the rename: no type change for users
    old = [_model("OrderTaxLine", shape), _model("Order", [_f("tax_lines", "array<OrderTaxLine>")])]
    new = [_model("OrderTaxLines", shape),
           _model("Order", [_f("tax_lines", "array<OrderTaxLines>")])]  # fmt: skip
    follow = _one(_run(old, new), "tax_lines", "type")
    assert (follow["visibleToUsers"], follow["breaking"], follow.get("rename")) == (
        False, False, True,
    )  # fmt: skip
    assert report(items)[0]["rule"] == "A4-same-shape-rename"


def test_page_text_decides_confirmed_vs_suspect() -> None:
    old = [_ep([_f("id")])]
    new = [_ep([_f("id"), _f("currency", desc="ISO 4217 code.")])]
    changed = _run(old, new, PackageMeta(page_texts={URL: "id"}),
                   PackageMeta(page_texts={URL: "id. currency: ISO 4217 code."}))  # fmt: skip
    item = _one(changed, "currency", "added")
    assert (item["class"], item["visibleToUsers"]) == ("confirmed", True)
    assert item["evidence"]["quote"] == "ISO 4217 code."
    same = _run(old, new, PackageMeta(page_texts={URL: "same page"}),
                PackageMeta(page_texts={URL: "same page"}))  # fmt: skip
    item = _one(same, "currency", "added")
    assert item["class"] == "suspect"
    assert item["artifactRules"][0] == "P0-page-unchanged"
    assert not item["visibleToUsers"]
    nothing = _one(_run(old, new), "currency", "added")
    assert nothing["class"] == "unknown"  # no source evidence either way


def test_changelog_makes_likely_and_a_baseline_never_confirms() -> None:
    old, new = [_ep([_f("id")])], [_ep([_f("id"), _f("x")])]
    likely = _one(_run(old, new, meta_b=PackageMeta(changed_pages=frozenset({URL}))), "x", "added")
    assert (likely["class"], likely["visibleToUsers"]) == ("likely", True)
    baseline = PackageMeta(baseline_only=True, page_hashes={URL: "aaa"})
    item = _one(_run(old, new, baseline, PackageMeta(page_hashes={URL: "bbb"})), "x", "added")
    assert item["class"] == "unknown"  # a baseline says nothing about the old content


def test_extraction_artifacts_are_suspect_and_flagged() -> None:
    names = [f"f{i:02d}" for i in range(30)]
    old = [_ep([_f(n) for n in names])]
    new = [_ep([_f(n) for n in names[:10]])]  # alphabetical cut-off, 20 removed
    items = _run(old, new)
    removed = [i for i in items if i["op"] == "removed"]
    assert len(removed) == 20
    assert all(i["class"] == "suspect" for i in removed)
    assert {"A1-mass-removal", "A2-alphabetical-cutoff"} <= set(removed[0]["artifactRules"])
    reason = attention(items, None, 0.05)
    assert reason is not None
    assert "suspect breaking" in reason
    assert "mass removal" in reason
    assert counts(items)["breaking"] == 0  # suspect items are never visible
    text = issues_text({"api": "shop", "from": "b-a", "to": "b-b", "package": {},
                        "report": report(items)}, cap=5)  # fmt: skip
    assert "Mass removal (A1-mass-removal)" in text
    assert "+15 more, see the web report" in text


def test_quality_blockers_failed_pages_and_flapping() -> None:
    old, new = [_ep([_f("id"), _f("x")])], [_ep([_f("id")])]
    blocked = _one(_run(old, new, meta_b=PackageMeta(blocked_units=frozenset({"get-orders"}))),
                   "x", "removed")  # fmt: skip
    assert "A5-completeness-flag" in blocked["artifactRules"]
    unread = _one(_run(old, new, meta_b=PackageMeta(failed_pages=frozenset({URL}))), "x", "removed")
    assert "A6-unread-page" in unread["artifactRules"]
    previous = [{"subject": {"docId": "endpoint:GET~/orders", "fieldPath": "x"},
                 "kind": "response_field", "op": "added"}]  # fmt: skip
    flap = _one(_run(old, new, previous=previous), "x", "removed")
    assert ("A7-flapping" in flap["artifactRules"], flap["class"]) == (True, "suspect")


def test_ids_are_stable_across_recomputation() -> None:
    old, new = [_ep([_f("id")])], [_ep([_f("id"), _f("x")])]
    assert [i["id"] for i in _run(old, new)] == [i["id"] for i in _run(old, new)]
    other = replace(new[0], title="List all orders")
    assert [i["id"] for i in _run(old, [other])] != []


def test_page_urls_match_with_or_without_a_trailing_slash() -> None:
    old, new = [_ep([_f("id")])], [_ep([_f("id"), _f("x", desc="New x.")])]
    a = PackageMeta(page_hashes={URL + "/": "h1"}, page_texts={URL + "/": "id"})
    b = PackageMeta(page_hashes={URL + "/": "h2"}, page_texts={URL + "/": "id x New x."},
                    changed_pages=frozenset({URL + "/"}))  # fmt: skip
    item = _one(_run(old, new, a, b), "x", "added")
    assert (item["class"], item["evidence"]["pageHashBefore"]) == ("confirmed", "h1")


def test_removals_and_newly_required_inputs_are_confirmed_from_the_new_page() -> None:
    q = FieldLocation.QUERY
    old = [_ep([_f("id"), _f("gone", desc="Old field."), _f("status", "string", q)])]
    new = [_ep([_f("id"), _f("status", "string", q, required=True)])]
    a = PackageMeta(page_hashes={URL: "h1"})  # the old text is not at hand (a later process)
    text = "- id\n- status (string, required): Order status."
    b = PackageMeta(page_hashes={URL: "h2"}, page_texts={URL: text})
    items = _run(old, new, a, b)
    gone = _one(items, "gone", "removed")
    assert (gone["class"], gone["breaking"], gone["visibleToUsers"]) == ("confirmed", True, True)
    status = _one(items, "status", "required")
    assert (status["class"], status["breakingReason"]) == ("confirmed", "newly required input")
    unchanged = PackageMeta(page_hashes={URL: "h1"}, page_texts=b.page_texts)
    assert _one(_run(old, new, a, unchanged), "gone", "removed")["class"] == "suspect"


def test_a_unit_attributed_to_a_spec_is_judged_by_the_spec() -> None:
    spec = "https://vendor.example/openapi.json"
    old, new = [_ep([_f("id")])], [_ep([_f("id"), _f("x", desc="New x.")])]
    attributed = {"get-orders": (spec,)}
    sources = ({"url": spec, "kind": "spec", "contentSha256": "s1"},)
    a = PackageMeta(sources=sources, unit_sources=attributed)
    b = PackageMeta(sources=({**sources[0], "contentSha256": "s2"},), unit_sources=attributed,
                    page_texts={spec: "x: New x."})  # fmt: skip
    item = _one(_run(old, new, a, b), "x", "added")
    assert item["class"] == "confirmed"  # the spec changed and says it
    assert (item["evidence"]["sourceKind"], item["evidence"]["attribution"]) == (
        "spec", "recorded",
    )  # fmt: skip
    same = PackageMeta(sources=sources, unit_sources=attributed, page_texts={spec: "x: New x."})
    assert _one(_run(old, new, a, same), "x", "added")["class"] == "suspect"  # spec unchanged
    plain = _one(_run(old, new), "x", "added")["evidence"]
    assert (plain["sourceKind"], plain["attribution"]) == (None, "not-recorded")  # never guess


def test_stream_conflicts_are_in_the_issues_text() -> None:
    conflict = {"unit": "get-orders", "field": "status", "chosen": "enum", "reason": "newer",
                "values": [{"url": "https://v/spec", "value": "string"}]}  # fmt: skip
    text = issues_text({"api": "shop", "from": "a", "to": "b", "package": {}, "report": [],
                        "conflicts": [conflict]})  # fmt: skip
    assert "Source conflicts stream reported (1)" in text
    assert "get-orders `status`: chosen enum (newer); values https://v/spec: string" in text
