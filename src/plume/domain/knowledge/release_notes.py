"""Release notes: what changed between two builds of one API, and whether the vendor docs
changed or only the extraction did (docs/design/release-notes.md).

Pure functions over documents. Every change is one item; its ``class`` says how sure Plume is
that the SOURCE changed:

- ``confirmed``: the vendor page's text changed and the new value is in it verbatim;
- ``likely``: stream's changelog names the page or unit (no verbatim check possible);
- ``suspect``: the page text is unchanged, or a known extraction artifact fires;
- ``unknown``: no source evidence either way.

Only confirmed and likely items are ever shown to users.
"""

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec

Item = dict[str, Any]  # one change (JSON-ready)

CONFIRMED, LIKELY, SUSPECT, UNKNOWN = "confirmed", "likely", "suspect", "unknown"
VISIBLE = (CONFIRMED, LIKELY)
MASS_SHARE = 0.30  # A1 / A3: more than this share of a document's fields gone
MASS_COUNT = 20  # ... or at least this many
ATTENTION_SUSPECT_BREAKING = 5
QUOTE_MAX = 500

RULES: dict[str, tuple[str, str]] = {
    "P0-page-unchanged": (
        "Vendor page unchanged",
        "The vendor page's text is the same in both packages, so the difference comes from the "
        "extraction, not from the docs.",
    ),
    "A1-mass-removal": (
        "Mass removal",
        "Many fields of one document disappeared at once while its page did not visibly change: "
        "typical of a truncated extraction.",
    ),
    "A2-alphabetical-cutoff": (
        "Alphabetical cut-off",
        "The removed fields are exactly the alphabetically last ones of the document: the "
        "extraction stopped part-way.",
    ),
    "A3-property-drop": (
        "Model properties dropped",
        "A model lost a large share of its properties while its page did not visibly change.",
    ),
    "A5-completeness-flag": (
        "Completeness or quality flag",
        "The package marks this document as incomplete, or stream's quality report has a "
        "blocker on it.",
    ),
    "A6-unread-page": (
        "Unread page",
        "Stream reports the vendor page as failed or unread in this run.",
    ),
    "A7-flapping": (
        "Flapping",
        "This change undoes a change from the previous build (present, absent, present again).",
    ),
    "A4-same-shape-rename": (
        "Same-shape rename",
        "A model was renamed with identical properties and types: no change for users.",
    ),
    "unknown": (
        "No source evidence",
        "Neither the page text nor stream's changelog says whether the docs changed.",
    ),
}


@dataclass(frozen=True, slots=True)
class PackageMeta:
    """What a package says about its extraction (read at load, kept per build)."""

    stream_version: str | None = None
    rules_hash: str | None = None
    run_id: str | None = None
    extracted_at: str | None = None
    failed_pages: frozenset[str] = frozenset()
    blocked_units: frozenset[str] = frozenset()  # unit (endpoint) ids with quality blockers
    # url -> cleanSha256 (pages.json; the page text after stream's cleaner, so page chrome
    # moving does not count as a docs change)
    page_hashes: Mapping[str, str] = field(default_factory=dict)
    changed_pages: frozenset[str] = frozenset()  # urls/unit ids named by stream's changelog
    # pages.json written after the extraction (baselineKind "snapshot-after-extraction"): a
    # baseline for the NEXT package only, never evidence about this package's own content
    baseline_only: bool = False
    llm_files: frozenset[str] = frozenset()  # files stream lists as LLM-written (vary per run)
    # url -> source snapshot text (_sources/<sha>.txt); kept in memory at load, not stored
    page_texts: Mapping[str, str] = field(default_factory=dict, compare=False)
    # manifest sources[]: {url, kind (docs|spec|changelog|sdk|other), fetchedAt, contentSha256,
    # etag, role}; a package without them falls back to its source.url as one docs source
    sources: tuple[Mapping[str, Any], ...] = ()
    changelog_urls: tuple[str, ...] = ()
    unit_sources: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # unit -> urls
    # stream's conflicts between sources: {unit, field, values: [{url, value}], chosen, reason}
    conflicts: tuple[Mapping[str, Any], ...] = ()
    conflicts_checked: frozenset[str] = frozenset()  # units stream compared
    conflicts_unchecked: frozenset[str] = frozenset()  # conflictsChecked: false (not compared)

    def as_json(self) -> dict[str, Any]:
        return {
            "streamVersion": self.stream_version,
            "rulesHash": self.rules_hash,
            "runId": self.run_id,
            "extractedAt": self.extracted_at,
            "failedPages": sorted(self.failed_pages),
            "blockedUnits": sorted(self.blocked_units),
            "pageHashes": dict(sorted(self.page_hashes.items())),
            "changedPages": sorted(self.changed_pages),
            "baselineOnly": self.baseline_only,
            "llmFiles": sorted(self.llm_files),
            "sources": [dict(x) for x in self.sources],
            "changelogUrls": list(self.changelog_urls),
            "unitSources": {u: list(v) for u, v in sorted(self.unit_sources.items())},
            "conflicts": [dict(x) for x in self.conflicts],
            "conflictsChecked": sorted(self.conflicts_checked),
            "conflictsUnchecked": sorted(self.conflicts_unchecked),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> "PackageMeta":
        d = data or {}
        return cls(
            d.get("streamVersion"),
            d.get("rulesHash"),
            d.get("runId"),
            d.get("extractedAt"),
            frozenset(d.get("failedPages") or ()),
            frozenset(d.get("blockedUnits") or ()),
            dict(d.get("pageHashes") or {}),
            frozenset(d.get("changedPages") or ()),
            bool(d.get("baselineOnly")),
            frozenset(d.get("llmFiles") or ()),
            sources=tuple(d.get("sources") or ()),
            changelog_urls=tuple(d.get("changelogUrls") or ()),
            unit_sources={u: tuple(v) for u, v in (d.get("unitSources") or {}).items()},
            conflicts=tuple(d.get("conflicts") or ()),
            conflicts_checked=frozenset(d.get("conflictsChecked") or ()),
            conflicts_unchecked=frozenset(d.get("conflictsUnchecked") or ()),
        )

    def source_kind(self, url: str | None) -> str | None:
        """The kind of the source a URL belongs to (docs, spec, changelog, sdk, other)."""
        target = _url(url)
        for src in self.sources:
            if target and _url(src.get("url")) == target:
                return str(src.get("kind") or "other")
        return None


# -- the diff ---------------------------------------------------------------------------------


_REQUEST = (FieldLocation.PATH, FieldLocation.QUERY, FieldLocation.HEADER, FieldLocation.BODY)


def _field_kind(doc: Document, f: FieldSpec) -> str:
    if doc.kind is DocumentKind.MODEL:
        return "property"
    if f.location in (FieldLocation.PATH, FieldLocation.QUERY, FieldLocation.HEADER):
        return "param"
    return "request_field" if f.location is FieldLocation.BODY else "response_field"


def _subject(doc: Document, f: FieldSpec | None = None) -> dict[str, Any]:
    return {
        "docId": doc.doc_id,
        "method": doc.method,
        "path": doc.path,
        "model": doc.title if doc.kind is DocumentKind.MODEL else None,
        "fieldPath": f.name if f else None,
        "location": f.location.value if f else None,
    }


def _quote(text: str | None) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    if len(flat) <= QUOTE_MAX:
        return flat
    cut = flat[:QUOTE_MAX].rsplit(" ", 1)[0]
    return cut + "…"


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("`", "").replace("*", "")).strip().lower()


def _model_key(d: Document) -> str:
    return (d.source_id or d.title).lower()


def _keyed(docs: Iterable[Document]) -> dict[tuple[str, str], Document]:
    out: dict[tuple[str, str], Document] = {}
    for d in docs:
        if d.kind.value not in _DOC_KIND:
            continue  # the app document is package metadata, not API surface
        if d.kind is DocumentKind.MODEL:
            out[("model", _model_key(d))] = d
        elif d.kind is DocumentKind.GUIDE:
            out[("guide", d.source_url or d.doc_id)] = d
        else:
            out[(d.kind.value, d.doc_id)] = d
    return out


_DOC_KIND = {
    "endpoint": "endpoint",
    "model": "model",
    "auth": "auth_scheme",
    "trigger": "webhook_event",
    "guide": "guide",
}


def _item(kind: str, op: str, doc: Document, f: FieldSpec | None = None, **more: Any) -> Item:
    return {"kind": kind, "op": op, "subject": _subject(doc, f), **more}


def _breaking_for_field(
    kind: str, op: str, before: FieldSpec | None, after: FieldSpec | None
) -> tuple[bool, str | None]:
    request = kind in ("param", "request_field")
    if op == "removed":
        return True, "removed field" if kind != "param" else "removed parameter"
    if op == "type":
        return (
            True,
            f"type changed {before.type if before else '?'} -> {after.type if after else '?'}",
        )
    if op == "required" and after is not None and after.required and request:
        return True, "newly required input"
    if op == "added" and after is not None and after.required and request:
        return True, "new required input"
    return False, None


def _field_items(a: Document, b: Document) -> list[Item]:
    out: list[Item] = []
    fa = {(f.location, f.name): f for f in a.fields}
    fb = {(f.location, f.name): f for f in b.fields}
    for key in sorted(set(fa) | set(fb), key=lambda k: (k[0].value, k[1])):
        before, after = fa.get(key), fb.get(key)
        doc_f = after or before
        if doc_f is None:  # pragma: no cover - a key comes from one side
            continue
        kind = _field_kind(b if after else a, doc_f)
        ops: list[str] = []
        if before is None:
            ops = ["added"]
        elif after is None:
            ops = ["removed"]
        else:
            if (before.type or "") != (after.type or ""):
                ops.append("type")
            if before.required != after.required:
                ops.append("required")
            if _norm(before.description) != _norm(after.description):
                ops.append("description")
        for op in ops:
            breaking, reason = _breaking_for_field(kind, op, before, after)
            out.append(
                _item(
                    kind,
                    op,
                    b if after else a,
                    doc_f,
                    before=_value(before),
                    after=_value(after),
                    breaking=breaking,
                    breakingReason=reason,
                )
            )
    return out


def _value(f: FieldSpec | Document | None) -> Item | None:
    if f is None:
        return None
    if isinstance(f, Document):
        return {"quote": _quote(f.title)}
    return {"type": f.type, "required": f.required, "quote": _quote(f.description)}


def _same_shape(a: Document, b: Document) -> bool:
    if a.shape and b.shape:
        return a.shape == b.shape
    return {(f.name, f.type) for f in a.fields} == {(f.name, f.type) for f in b.fields} and bool(
        a.fields
    )


def _changed_items(kind: str, a: Document, b: Document) -> list[Item]:
    """Differences of a document present in both builds."""
    out: list[Item] = []
    if kind in ("endpoint", "model"):
        out.extend(_field_items(a, b))
        for s in sorted(set(b.scopes) - set(a.scopes)):
            out.append(
                _item(
                    "scope",
                    "added",
                    b,
                    before=None,
                    after={"quote": s},
                    breaking=True,
                    breakingReason=f"newly required scope {s}",
                )
            )
        for s in sorted(set(a.scopes) - set(b.scopes)):
            out.append(
                _item(
                    "scope",
                    "removed",
                    b,
                    before={"quote": s},
                    after=None,
                    breaking=False,
                    breakingReason=None,
                )
            )
    if kind not in {"endpoint", "model"} and _norm(a.text) != _norm(b.text):
        out.append(
            _item(
                kind,
                "description",
                b,
                before={"quote": _quote(a.text)},
                after={"quote": _quote(b.text)},
                breaking=False,
                breakingReason=None,
            )
        )
    if a.complete != b.complete:
        out.append(
            _item(
                kind,
                "completeness",
                b,
                before={"quote": str(a.complete)},
                after={"quote": str(b.complete)},
                breaking=False,
                breakingReason=None,
            )
        )
    return out


def diff_documents(old: Sequence[Document], new: Sequence[Document]) -> list[Item]:
    """Every atomic difference between two builds' documents (unclassified)."""
    ka, kb = _keyed(old), _keyed(new)
    out: list[Item] = []
    removed_models = [k for k in ka if k not in kb and k[0] == "model"]
    added_models = [k for k in kb if k not in ka and k[0] == "model"]
    renamed: dict[tuple[str, str], tuple[str, str]] = {}
    for r in removed_models:  # same-shape renames (OrderTaxLine -> OrderTaxLines)
        for n in added_models:
            if n not in renamed.values() and _same_shape(ka[r], kb[n]):
                renamed[r] = n
                break
    for r, n in renamed.items():
        out.append(
            _item(
                "model",
                "renamed",
                kb[n],
                before={"quote": ka[r].title},
                after={"quote": kb[n].title},
                breaking=False,
                breakingReason=None,
                rename=True,
            )
        )
    titles: dict[str, str] = {}  # old -> new name of each renamed model (title and file stem)
    for r, n in renamed.items():
        titles[ka[r].title.lower()] = kb[n].title.lower()
        titles[ka[r].doc_id.split(":", 1)[1]] = kb[n].doc_id.split(":", 1)[1]
    start = len(out)
    for key in sorted(set(ka) | set(kb)):
        if key in renamed or key in renamed.values():
            continue
        a, b = ka.get(key), kb.get(key)
        doc = b or a
        if doc is None:  # pragma: no cover
            continue
        kind = _DOC_KIND[key[0]]
        if a is None or b is None:
            op = "added" if a is None else "removed"
            breaking = op == "removed" and kind in (
                "endpoint",
                "model",
                "auth_scheme",
                "webhook_event",
            )
            out.append(
                _item(
                    kind,
                    op,
                    doc,
                    before=_value(a),
                    after=_value(b),
                    breaking=breaking,
                    breakingReason=f"removed {kind.replace('_', ' ')}" if breaking else None,
                )
            )
            continue
        out.extend(_changed_items(kind, a, b))
    for it in out[start:]:  # a field typed with a renamed model follows the rename
        if it["op"] == "type" and _follows_rename(it, titles):
            it.update(rename=True, breaking=False, breakingReason=None)
    return out


def _follows_rename(item: Item, titles: Mapping[str, str]) -> bool:
    before = str((item.get("before") or {}).get("type") or "").lower()
    after = str((item.get("after") or {}).get("type") or "").lower()
    return any(old in before and before.replace(old, new) == after for old, new in titles.items())


# -- classification ----------------------------------------------------------------------------


def _url(url: str | None) -> str:
    return (url or "").split("#", 1)[0].rstrip("/")


def page_texts(meta: PackageMeta) -> dict[str, str]:
    """Vendor page text per URL: stream's source snapshots (pages.json -> _sources/), read at
    load. NOT the knowledge-export pages: those are LLM-written and vary between runs, so they
    cannot prove (or disprove) a docs change."""
    return {_url(u): t for u, t in meta.page_texts.items()}


def text_hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode()).hexdigest()[:16]


def in_text(value: str | None, text: str | None) -> bool:
    return bool(value) and bool(text) and _norm(value) in _norm(text)


def _leaf(path: str | None) -> str:
    return (path or "").replace("[]", "").rsplit(".", 1)[-1]


def _near(name: str | None, word: str, text: str | None, span: int = 60) -> bool:
    """``word`` within ``span`` characters after ``name`` (e.g. "status (string, required)")."""
    if not name or not text:
        return False
    flat = _norm(text)
    return any(
        word in flat[m.end() : m.end() + span]
        for m in re.finditer(rf"(?<![\w.]){re.escape(name.lower())}(?![\w])", flat)
    )


def _verbatim(item: Item, old_text: str | None, new_text: str | None) -> tuple[bool, str | None]:
    """Is the change visible in the source text? Returns (holds, quote from B)."""
    op = item["op"]
    name = _leaf(item["subject"].get("fieldPath")) or (item["after"] or {}).get("quote")
    after = item.get("after") or {}
    before = item.get("before") or {}
    if op == "removed":
        old_quote = before.get("quote") or name
        if new_text is None:
            return False, None
        # The old page text is usually not at hand (snapshots are read at load, only hashes
        # are kept), so a removal holds when the changed page no longer has the value.
        was_there = old_text is None or in_text(old_quote, old_text)
        return was_there and not in_text(old_quote, new_text), None
    if op == "required":
        holds = bool(after.get("required")) and _near(name, "required", new_text)
        return holds, name
    if op == "added":
        quote = after.get("quote")
        holds = in_text(name, new_text) and (not quote or in_text(quote, new_text))
        return holds, quote or name
    if op == "description":
        return in_text(after.get("quote"), new_text), after.get("quote")
    typ = after.get("type")  # op == "type" (other ops never hold)
    return op == "type" and bool(typ) and _near(name, str(typ), new_text, 40), name


def _top(path: str) -> str:
    return path.split(".", 1)[0].replace("[]", "")


def _document_artifacts(
    items: Sequence[Item], docs_a: Mapping[str, Document], docs_b: Mapping[str, Document]
) -> tuple[set[str], set[str]]:
    """Documents with a mass removal (A1/A3) and with an alphabetical cut-off (A2)."""
    removed_by_doc: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        if it["op"] == "removed" and it["subject"].get("fieldPath"):
            removed_by_doc[it["subject"]["docId"]].append(it)
    mass: set[str] = set()
    cutoff: set[str] = set()
    for doc_id, removed in removed_by_doc.items():
        a = docs_a.get(doc_id)
        if a is None or not a.fields:
            continue
        if len(removed) >= MASS_COUNT or len(removed) / len(a.fields) > MASS_SHARE:
            mass.add(doc_id)
        b = docs_b.get(doc_id)
        kept = {_top(f.name) for f in (b.fields if b else ())}
        tops = sorted({_top(f.name) for f in a.fields})
        gone = {_top(r["subject"]["fieldPath"]) for r in removed} - kept
        if len(removed) >= 3 and gone and len(gone) < len(tops) and set(tops[-len(gone) :]) == gone:
            cutoff.add(doc_id)
    return mass, cutoff


@dataclass(frozen=True, slots=True)
class _Context:
    docs_a: Mapping[str, Document]
    docs_b: Mapping[str, Document]
    pages_a: Mapping[str, str]
    pages_b: Mapping[str, str]
    meta_old: PackageMeta
    meta_new: PackageMeta
    mass: set[str]
    cutoff: set[str]
    previous: set[tuple[Any, ...]]
    # the metas' URL-keyed values with URLs normalised like documents' (no fragment or
    # trailing slash), so ".../orders/" in pages.json matches a document's ".../orders"
    hashes_a: Mapping[str, str] = field(default_factory=dict)
    hashes_b: Mapping[str, str] = field(default_factory=dict)
    changed: frozenset[str] = frozenset()
    failed: frozenset[str] = frozenset()


_INVERSE = {"added": "removed", "removed": "added"}


def _hashes(meta: PackageMeta) -> dict[str, str]:
    """Page hashes (pages.json) plus whole-source hashes (manifest sources[], e.g. a spec)."""
    out = {
        _url(s.get("url")): str(s.get("contentSha256") or s.get("etag"))
        for s in meta.sources
        if s.get("url") and (s.get("contentSha256") or s.get("etag"))
    }
    out.update({_url(u): h for u, h in meta.page_hashes.items()})
    return out


def _rules(it: Item, doc: Document | None, url: str, ctx: _Context) -> list[str]:
    subj = it["subject"]
    rules: list[str] = []
    if it.get("rename"):
        rules.append("A4-same-shape-rename")
    removal = it["op"] == "removed" and bool(subj.get("fieldPath"))
    if removal and subj["docId"] in ctx.mass:
        rules.append("A3-property-drop" if subj.get("model") else "A1-mass-removal")
    if removal and subj["docId"] in ctx.cutoff:
        rules.append("A2-alphabetical-cutoff")
    unit = doc.source_id if doc else None
    if it["op"] == "completeness" or (unit and unit in ctx.meta_new.blocked_units):
        rules.append("A5-completeness-flag")
    if url and url in ctx.failed:
        rules.append("A6-unread-page")
    flip = (subj.get("docId"), subj.get("fieldPath"), it["kind"], _INVERSE.get(it["op"]))
    if it["op"] in _INVERSE and flip in ctx.previous:
        rules.append("A7-flapping")
    return rules


def _side(
    urls: Sequence[str], pages: Mapping[str, str], hashes: Mapping[str, str]
) -> tuple[str | None, str | None]:
    texts = [pages[u] for u in urls if u in pages]
    known = [hashes.get(u) or (text_hash(pages[u]) if u in pages else None) for u in urls]
    digest = "+".join(h for h in known if h) if all(known) and known else None
    return ("\n".join(texts) or None), digest


def _classify_one(it: Item, ctx: _Context) -> None:
    subj = it["subject"]
    doc = ctx.docs_b.get(subj["docId"]) or ctx.docs_a.get(subj["docId"])
    url = _url(doc.source_url if doc else None)
    unit = doc.source_id if doc else None
    # The sources stream attributes the unit to (a spec and/or docs pages), else its page.
    attributed = ctx.meta_new.unit_sources.get(unit or "") or ctx.meta_old.unit_sources.get(
        unit or ""
    )
    urls = sorted({_url(u) for u in attributed}) if attributed else ([url] if url else [])
    ta, ha = _side(urls, ctx.pages_a, ctx.hashes_a)
    tb, hb = _side(urls, ctx.pages_b, ctx.hashes_b)
    if ctx.meta_old.baseline_only and any(u in ctx.hashes_a for u in urls):
        ha = None  # a baseline written after the old extraction says nothing about its content
    rules = _rules(it, doc, url, ctx)
    holds, quote = _verbatim(it, ta, tb) if (ta or tb) else (False, None)
    page_changed = None if (ha is None or hb is None) else ha != hb
    named = bool(url and url in ctx.changed) or bool(unit and unit in ctx.changed)
    if it.get("rename"):
        cls = UNKNOWN  # never shown: no change for users
    elif page_changed and holds:
        cls = CONFIRMED
    elif page_changed is False:
        cls = SUSPECT
        rules.insert(0, "P0-page-unchanged")
    elif any(r != "A4-same-shape-rename" for r in rules):
        cls = SUSPECT
    elif named:
        cls = LIKELY
    else:
        cls = UNKNOWN
    it["class"] = cls
    it["computedClass"] = cls
    it["artifactRules"] = rules
    # Spec vs docs only from stream's recorded attribution; older builds: "not recorded".
    kinds = sorted({ctx.meta_new.source_kind(u) or "other" for u in urls}) if attributed else []
    it["evidence"] = {
        "sourceUrl": doc.source_url if doc else None,
        "sources": urls if attributed else [],
        "sourceKind": kinds[0] if len(kinds) == 1 else ("mixed" if kinds else None),
        "attribution": "recorded" if attributed else "not-recorded",
        "anchor": (doc.anchor or "").lstrip("#") or None if doc else None,
        "quote": _quote(quote) if cls == CONFIRMED else None,
        "pageHashBefore": ha,
        "pageHashAfter": hb,
        "changelog": named or None,
    }


def classify(
    items: list[Item],
    old: Sequence[Document],
    new: Sequence[Document],
    meta_old: PackageMeta,
    meta_new: PackageMeta,
    previous_items: Sequence[Item] = (),
) -> list[Item]:
    """Set class, evidence and artifact rules on each item (in place) and return them."""
    docs_a = {d.doc_id: d for d in old}
    docs_b = {d.doc_id: d for d in new}
    mass, cutoff = _document_artifacts(items, docs_a, docs_b)
    ctx = _Context(
        docs_a,
        docs_b,
        page_texts(meta_old),
        page_texts(meta_new),
        meta_old,
        meta_new,
        mass,
        cutoff,
        {
            (p["subject"].get("docId"), p["subject"].get("fieldPath"), p["kind"], p["op"])
            for p in previous_items
        },
        _hashes(meta_old),
        _hashes(meta_new),
        frozenset(_url(u) if "://" in u else u for u in meta_new.changed_pages),
        frozenset(_url(u) for u in meta_new.failed_pages),
    )
    for it in items:
        _classify_one(it, ctx)
    return items


def finish(
    items: list[Item], api: str, from_build: str, to_build: str, docs_as_of: str
) -> list[Item]:
    """Stable ids, build ids, visibility and wordingOnly; sorted for display."""
    for it in items:
        s = it["subject"]
        key = "\x00".join(
            str(x)
            for x in (
                api,
                from_build,
                to_build,
                it["kind"],
                s.get("docId"),
                s.get("fieldPath"),
                s.get("location"),
                it["op"],
            )
        )
        it["id"] = "ch-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        it["from"], it["to"], it["toDocsAsOf"] = from_build, to_build, docs_as_of
        it["wordingOnly"] = it["op"] == "description"
        it["visibleToUsers"] = it["class"] in VISIBLE and not it.get("rename")
    items.sort(
        key=lambda i: (
            not i["breaking"],
            i["kind"],
            i["subject"].get("docId") or "",
            i["subject"].get("fieldPath") or "",
            i["op"],
        )
    )
    return items


# -- summary, report, issues -------------------------------------------------------------------


def counts(items: Sequence[Item]) -> dict[str, Any]:
    by_class: dict[str, int] = defaultdict(int)
    for i in items:
        if not i.get("rename"):
            by_class[i["class"]] += 1
    visible = [i for i in items if i["visibleToUsers"]]
    by_kind: dict[str, int] = defaultdict(int)
    for i in visible:
        by_kind[i["kind"]] += 1
    return {
        "confirmed": by_class[CONFIRMED],
        "likely": by_class[LIKELY],
        "suspect": by_class[SUSPECT],
        "unknown": by_class[UNKNOWN],
        "renamed": sum(1 for i in items if i.get("rename")),
        "breaking": sum(1 for i in visible if i["breaking"]),
        "wordingOnly": sum(1 for i in visible if i["wordingOnly"]),
        "byKind": dict(sorted(by_kind.items())),
        "total": len(items),
    }


def attention(items: Sequence[Item], gold: Mapping[str, Any] | None, max_drop: float) -> str | None:
    """One plain line when the review needs a maintainer soon (never blocks), else None."""
    reasons: list[str] = []
    suspect = [i for i in items if i["class"] == SUSPECT]
    removed_endpoints = sum(1 for i in suspect if i["kind"] == "endpoint" and i["op"] == "removed")
    if removed_endpoints:
        reasons.append(f"{removed_endpoints} suspect removed endpoint(s)")
    breaking = sum(1 for i in suspect if i["breaking"])
    if breaking >= ATTENTION_SUSPECT_BREAKING:
        reasons.append(f"{breaking} suspect breaking changes")
    mass = {
        i["subject"]["docId"]
        for i in items
        if {"A1-mass-removal", "A3-property-drop"} & set(i["artifactRules"])
    }
    if mass:
        reasons.append(f"mass removal in {len(mass)} document(s)")
    if gold and gold.get("before") and gold.get("after"):
        drop = gold["before"]["recall_at_k"] - gold["after"]["recall_at_k"]
        if drop > max_drop:
            reasons.append(f"gold recall dropped {drop:.2f}")
    return "; ".join(reasons) or None


def report(items: Sequence[Item], limit: int | None = None) -> list[dict[str, Any]]:
    """Suspect and unknown items grouped by their first rule (and renames), for maintainers.
    With ``limit``, each group carries its first ``limit`` items (``count`` has them all)."""
    groups: dict[str, list[Item]] = defaultdict(list)
    for i in items:
        if i.get("rename"):
            groups["A4-same-shape-rename"].append(i)
        elif i["class"] == SUSPECT:
            first = next((r for r in i["artifactRules"] if r in RULES), "unknown")
            groups[first].append(i)
        elif i["class"] == UNKNOWN:
            groups["unknown"].append(i)
    order = list(RULES)
    return [
        {
            "rule": r,
            "title": RULES[r][0],
            "explanation": RULES[r][1],
            "count": len(groups[r]),
            "items": groups[r] if limit is None else groups[r][:limit],
        }
        for r in sorted(groups, key=order.index)
    ]


def issues_text(notes: Mapping[str, Any], fmt: str = "markdown", cap: int = 200) -> str:
    """The extraction report as one ready-to-paste text for stream."""
    md = fmt == "markdown"
    pkg = notes.get("package") or {}
    a, b = pkg.get("from") or {}, pkg.get("to") or {}
    lines = [
        ("# " if md else "")
        + f"Plume extraction report: {notes['api']} {notes['from']} -> {notes['to']}",
        "",
        f"- stream {a.get('streamVersion')} rules {str(a.get('rulesHash'))[:12]} run "
        f"{a.get('runId')} -> stream {b.get('streamVersion')} rules "
        f"{str(b.get('rulesHash'))[:12]} run {b.get('runId')}",
        "",
    ]
    shown = 0
    total = 0
    for group in notes.get("report", []):
        if group["rule"] == "A4-same-shape-rename":
            continue
        lines.append(("## " if md else "") + f"{group['title']} ({group['rule']})")
        lines.append(group["explanation"])
        for i in group["items"]:
            total += 1
            if shown >= cap:
                continue
            shown += 1
            s = i["subject"]
            where = s.get("fieldPath") or s.get("model") or s.get("docId")
            before = i.get("before") or {}
            after = i.get("after") or {}
            ev = i.get("evidence") or {}
            lines.append(
                f"- {i['kind']} {i['op']}: `{where}` in `{s.get('docId')}`; before "
                f"{before.get('type') or before.get('quote') or '-'}; after "
                f"{after.get('type') or after.get('quote') or '-'}; source "
                f"{ev.get('sourceUrl') or '-'}; page hash {ev.get('pageHashBefore') or '-'} -> "
                f"{ev.get('pageHashAfter') or '-'}"
            )
        lines.append("")
    if total > shown:
        lines.append(f"+{total - shown} more, see the web report")
    conflicts = notes.get("conflicts") or []
    if conflicts:
        title = f"Source conflicts stream reported ({len(conflicts)})"
        lines += ["", ("## " if md else "") + title]
        for c in conflicts[:cap]:
            values = "; ".join(f"{v.get('url')}: {v.get('value')}" for v in c.get("values") or [])
            lines.append(
                f"- {c.get('unit') or '-'} `{c.get('field') or '-'}`: chosen "
                f"{c.get('chosen')!s} ({c.get('reason') or '-'}); values {values or '-'}"
            )
    text = "\n".join(lines).rstrip() + "\n"
    return text if md else text.replace("`", "")
