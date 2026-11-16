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
