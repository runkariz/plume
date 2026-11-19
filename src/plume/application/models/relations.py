"""Relation candidates between concepts, from documented evidence only (no LLM, nothing invented).

See docs/design/model-relations.md §2. Per API, four kinds of evidence:

- ``nested``: a model/response field path nests another concept (``products[].variants[].id``:
  Product contains Variant).
- ``sub_resource``: an endpoint path ``/{parent}/{parent_id}/{child}`` (``/products/{product_id}/
  variants.json``).
- ``id_field``: a field ``<x>_id`` / ``<x>_ids`` / ``parent_id`` whose DESCRIPTION names the
  target concept ("The ID of the order the refund is associated with.").
- ``model_ref``: a field whose documented type names another concept's model.

A candidate is directional, parent → child (the side that contains, or is referenced by, the
other). Its ``options`` are only the designs the evidence supports, each with what it needs. Names
that differ across APIs are never merged; an ``alias`` candidate is offered only with structural
evidence in BOTH APIs (each a child of the same, exactly matching parent), for the user to accept.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from plume.application.models.concepts import (
    NOISE,
    ModelInputError,
    concept_docs,
    concept_key,
    concept_label,
    last_literal,
    resolve_apis,
    tidy_concept,
)
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.fact_index import FactIndex
from plume.application.ports.search_index import DocumentSummary, SearchIndex
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.domain.knowledge.fact import FactKind

_BODY = (None, FieldLocation.MODEL, FieldLocation.RESPONSE, FieldLocation.BODY)
_ID = re.compile(r"^(?P<stem>[a-z0-9_]+?)_(?P<plural>id|ids)$")
_PARAM = re.compile(r"^\{[^}]+\}$")
MAX_EVIDENCE_PER_KIND = 3
KINDS = ("nested", "sub_resource", "id_field", "model_ref")


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    kind: str  # nested | sub_resource | id_field | model_ref
    doc_id: str
    quote: str  # copied from the document (a field description or the document title)
    paths: tuple[str, ...] = ()  # documented field paths (the container, the id field)
    fetch: str | None = None  # "GET /products/{product_id}/variants.json" (sub_resource)
    many: bool = False  # an array / collection / *_ids: the child side is "many"
    read: bool = True  # from a model or a response (False: a request body only)


@dataclass(frozen=True, slots=True)
class RelationOption:
    kind: str  # embedded | reference
    cardinality: str  # 1:1 | 1:n | n:1 | n:m
    needs: str  # what the design requires, in words


@dataclass
class RelationCandidate:
    parent: str  # concept key
    child: str
    sources: dict[str, list[CandidateEvidence]] = field(default_factory=dict)  # api -> evidence

    @property
    def id(self) -> str:
        return f"{self.parent}>{self.child}"

    def kinds(self, api: str) -> list[str]:
        return sorted({e.kind for e in self.sources.get(api, [])}, key=KINDS.index)

    def options(self, labels: dict[str, str]) -> list[RelationOption]:
        ev = [e for es in self.sources.values() for e in es]
        parent, child = labels[self.parent], labels[self.child]
        many = any(e.many for e in ev)
        out: list[RelationOption] = []
        if any(e.kind in ("nested", "sub_resource", "model_ref") for e in ev):
            out.append(
                RelationOption(
                    "embedded",
                    "1:n" if many else "1:1",
                    f"a field of {parent} holding {child}"
                    + (" items (an array)" if many else " (an object)"),
                )
            )
        ids = [e for e in ev if e.kind in ("id_field", "sub_resource")]
        if ids:
            plural = any(e.kind == "id_field" and e.many for e in ids)
            out.append(
                RelationOption(
                    "reference",
                    "n:m" if plural else "n:1",
                    f"{child} maps an id field of {parent} (e.g. {self.parent}_id)",
                )
            )
        return out


@dataclass(frozen=True, slots=True)
class AliasCandidate:
    """Two differently named concepts in two APIs at the same documented position."""

    parent: str
    names: dict[str, str]  # api -> child concept key in that API
    evidence: dict[str, CandidateEvidence]  # api -> the structural evidence


@dataclass(frozen=True, slots=True)
class RelatedConcept:
    key: str
    name: str
    candidates: tuple[RelationCandidate, ...]
    kinds: dict[str, tuple[str, ...]]  # api -> evidence kinds
    evidence: int


@dataclass(frozen=True, slots=True)
class RelatedConcepts:
    apis: tuple[ResolvedBuild, ...]
    concept: str
    name: str
    related: tuple[RelatedConcept, ...]
    total: int
    aliases: tuple[AliasCandidate, ...]
    labels: dict[str, str]
    limit: int = 24
    offset: int = 0


@dataclass
class _Api:
    groups: dict[str, list[DocumentSummary]]
    names: dict[str, str]
    owner: dict[str, str]  # doc id -> concept key
    sub: set[str] = field(default_factory=set)  # endpoints listing a sub-collection (downloads)
    merge: dict[str, str] = field(default_factory=dict)  # duplicate concept key -> kept key
    # (owning concept, container key) -> the item model's concept: order.line_items are
    # Order Line Items, also where an endpoint shows the same container without schema files.
    items: dict[tuple[str, str], str] = field(default_factory=dict)


# Containers that wrap or link rather than hold a concept: _links / previous / next / self, and
# id lists (product_ids).
_WRAPPERS = frozenset({"previous", "next", "self", "links", "link", "embedded", "meta"})


def _referenced_concept(fields: Any, path: str, concepts: set[str]) -> str | None:
    """A container whose fields come from another schema file (`line_items` ->
    orderlineitem.schema.json) stands for that model's concept, when it is one."""
    prefixes = (f"{path}[].", f"{path}.")
    stems = {
        (f.pointer or "").split("#", 1)[0].rsplit("/", 1)[-1].removesuffix(".schema.json")
        for f in fields
        if f.pointer and any(f.name.startswith(x) and "." not in f.name[len(x) :] for x in prefixes)
    }  # direct children only (deeper ones belong to nested item models)
    keys = {concept_key(st) for st in stems if st}
    found = sorted(k for k in keys if k in concepts)
    return found[0] if len(found) == 1 else None


def _record_merge(scan: _Api, owner: str | None, container: str, item: str) -> None:
    """An item model named after its holder and container (productimage for product.images,
    customcollectioncollect for collects[] where Collect is a resource) is the container's
    concept: one name across APIs. Otherwise the container stands for its item model, but only
    under the same owning concept."""
    key = _segment_key(container.rsplit(".", 1)[-1])
    if not key or key == item:
        return
    if item == f"{owner}{key}" or (
        item.endswith(key)
        and key in scan.groups
        and any(d.kind is DocumentKind.ENDPOINT for d in scan.groups[key])
    ):  # productimage under product.images = Image; orderlineitem under order = Line Item
        scan.merge.setdefault(item, key)
    elif owner:
        scan.items.setdefault((owner, key), item)


def _read(spec: Any, method: str | None) -> bool:
    """Where the API is read: a model, or a GET response (a batch POST echoes its request)."""
    if spec is None:
        return method in (None, "GET")
    if spec.location is FieldLocation.MODEL:
        return True
    return spec.location is FieldLocation.RESPONSE and method == "GET"


def _ranked(bucket: list[CandidateEvidence]) -> list[CandidateEvidence]:
    """Model/response evidence first; request-body-only evidence is dropped when the API also
    documents the relation where it is read (WooCommerce product.images[] over the
    create[]/update[] paths of POST /products/batch). Then at most MAX_EVIDENCE_PER_KIND each."""
    if any(e.read for e in bucket):
        bucket = [e for e in bucket if e.read]
    out: list[CandidateEvidence] = []
    for e in bucket:
        if sum(x.kind == e.kind for x in out) < MAX_EVIDENCE_PER_KIND:
            out.append(e)
    return out


def _wrapper(seg: str) -> bool:
    name = seg.replace("[]", "").lower()
    return name.startswith("_") or name in _WRAPPERS or name.endswith(("_id", "_ids"))


ALIAS_SIMILARITY = 0.75
# Action endpoints (/orders/{id}/cancel.json) are operations, not child collections.
_ACTIONS = frozenset(
    {
        "cancel", "close", "open", "reopen", "complete", "approve", "accept", "refuse",
        "reject", "send", "calculate", "adjust", "set", "connect", "activate", "deactivate",
        "archive", "unarchive", "fulfill", "hold", "release", "move", "reschedule",
        "validate", "export", "import", "duplicate", "publish", "unpublish", "action",
        "cancelation", "cancellation", "refresh", "retry", "resend", "sync", "test",
    }
)  # fmt: skip


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _segment_key(seg: str) -> str:
    return concept_key(seg.replace("[]", "").split(".", 1)[0])


def _names_concept(text: str, key: str, label: str) -> bool:
    words = {label.lower(), key, key + "s", label.lower() + "s"}
    if key.endswith("y"):
        words.add(key[:-1] + "ies")
    low = text.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in words if w)


class SuggestRelated:
    def __init__(
        self,
        resolver: BuildResolver,
        index: SearchIndex,
        facts: FactIndex,
        documents: DocumentRepo,
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._facts = facts
        self._documents = documents

    def _scan(self, r: ResolvedBuild) -> _Api:
        summaries, _ = self._index.browse(r.build.build_id, (), None, 100_000, 0)
        groups = concept_docs(summaries)
        names: dict[str, str] = {}
        for key, docs in groups.items():
            for d in docs:
                own = ((d.resource if d.kind is DocumentKind.ENDPOINT else d.title) or "").split(
                    " / "
                )[-1]
                if concept_key(own) == key:
                    names[key] = concept_label(own)
                    break
            names.setdefault(key, concept_label(key))
        owner = {d.doc_id: k for k, docs in groups.items() for d in docs}
        # /customers/{id}/downloads lists downloads, not customers: its top-level id fields
        # are not the customer's (WooCommerce "Customer" / "Report" noise).
        sub = set()
        for key, docs in groups.items():
            for d in docs:
                if d.kind is DocumentKind.ENDPOINT and d.path:
                    last = concept_key(last_literal(d.path))
                    if last and not key.endswith(last):
                        sub.add(d.doc_id)
        return _Api(groups, names, owner, sub)

    def candidates(
        self,
        resolved: tuple[ResolvedBuild, ...],
        renames: dict[tuple[str, str], str] | None = None,
    ) -> tuple[list[RelationCandidate], list[AliasCandidate], dict[str, str]]:
        """Every candidate between concepts of these APIs, with the concept labels.
        `renames` {(api, concept key in that API): concept key}: accepted aliases (D2), so
        WooCommerce "variation" evidence counts for "variant"."""
        found: dict[tuple[str, str], RelationCandidate] = {}
        labels: dict[str, str] = {}
        structural: dict[str, dict[str, dict[str, CandidateEvidence]]] = defaultdict(dict)
        scans = {r.api.api_id.value: self._scan(r) for r in resolved}
        # A concept documented in one API can be nested in another (WooCommerce product.images[]
        # has no Image model of its own, Shopify has one).
        all_concepts = {k for s in scans.values() for k in s.groups}
        renames = renames or {}
        for r in resolved:
            api = r.api.api_id.value
            scan = scans[api]
            raw = self._evidence(r, scan, all_concepts)  # may add labels and merges

            def canon(k: str, doc_id: str, api: str = api, scan: _Api = scan) -> str:
                owner = scan.owner.get(doc_id)
                if owner and k != owner:
                    k = scan.items.get((owner, k), k)
                k = scan.merge.get(k, k)
                return renames.get((api, k), k)

            evidence = [
                (cp, cc, ev)
                for p, c, ev in raw
                if (cp := canon(p, ev.doc_id)) != (cc := canon(c, ev.doc_id))
            ]
            for k, v in scan.names.items():
                labels.setdefault(k, v)
            # An id field is evidence both ways: order.customer_id is "a customer has orders"
            # and "an order references its customer" (set-g1: Woo's customer_id was only under
            # customer>order).
            evidence += [(c, p, ev) for p, c, ev in evidence if ev.kind == "id_field"]
            for parent, child, ev in evidence:
                cand = found.setdefault((parent, child), RelationCandidate(parent, child))
                cand.sources.setdefault(api, []).append(ev)  # ranked and capped below
                if ev.kind in ("nested", "sub_resource"):
                    known = structural[parent].setdefault(api, {})
                    prior = known.get(child)
                    if prior is None or (
                        not (prior.fetch or "").startswith("GET ")
                        and (ev.fetch or "").startswith("GET ")
                    ):  # prefer the listing endpoint as the cited evidence
                        known[child] = ev
        for cand in found.values():
            for api, bucket in cand.sources.items():
                cand.sources[api] = _ranked(bucket)
        aliases = self._aliases(resolved, structural, found)
        return sorted(found.values(), key=lambda c: c.id), aliases, labels

    def _aliases(
        self,
        resolved: tuple[ResolvedBuild, ...],
        structural: dict[str, dict[str, dict[str, CandidateEvidence]]],
        found: dict[tuple[str, str], RelationCandidate],
    ) -> list[AliasCandidate]:
        """D2: children of the same parent in two APIs, each absent from the other API, both
        documented as collections (an array or a sub-resource). Close names only (a filter that
        narrows the list; it never links anything by itself): the user accepts or not."""
        present: dict[str, set[str]] = defaultdict(set)  # api -> concepts with any evidence
        for (p, c), cand in found.items():
            for api in cand.sources:
                present[api].update((p, c))
        apis = [r.api.api_id.value for r in resolved]
        out: list[AliasCandidate] = []
        for parent, per_api in sorted(structural.items()):
            for i, a1 in enumerate(apis):
                for a2 in apis[i + 1 :]:
                    for c1, e1 in sorted(per_api.get(a1, {}).items()):
                        for c2, e2 in sorted(per_api.get(a2, {}).items()):
                            if c1 == c2 or c1 in present[a2] or c2 in present[a1]:
                                continue
                            if not (e1.many and e2.many) or _similar(c1, c2) < ALIAS_SIMILARITY:
                                continue
                            out.append(AliasCandidate(parent, {a1: c1, a2: c2}, {a1: e1, a2: e2}))
        return out

    def _evidence(
        self, r: ResolvedBuild, scan: _Api, known: set[str] | None = None
    ) -> list[tuple[str, str, CandidateEvidence]]:
        concepts = set(scan.groups) | (known or set())
        out = self._sub_resources(scan, concepts)
        out += self._field_evidence(r, scan, concepts, self._field_hits(r, scan, concepts))
        return out

    def _sub_resources(
        self, scan: _Api, concepts: set[str]
    ) -> list[tuple[str, str, CandidateEvidence]]:
        """``/{parent}/{parent_id}/{child}`` endpoint paths."""
        out: list[tuple[str, str, CandidateEvidence]] = []
        # sub-resources: /{parent}/{parent_id}/{child}
        for docs in scan.groups.values():
            for d in docs:
                if d.kind is not DocumentKind.ENDPOINT or not d.path:
                    continue
                segs = [s.split(".", 1)[0] for s in d.path.strip("/").split("/")]
                for i in range(len(segs) - 2):
                    if _PARAM.match(segs[i]) or not _PARAM.match(segs[i + 1]):
                        continue
                    if _PARAM.match(segs[i + 2]):
                        continue
                    parent, child = concept_key(segs[i]), concept_key(segs[i + 2])
                    # The child may be a collection that is no concept of its own in this API
                    # (WooCommerce tags /products/{id}/variations with resource "Product").
                    if (
                        parent in concepts
                        and child
                        and child != parent
                        and child not in NOISE
                        and child not in _ACTIONS
                    ):
                        scan.names.setdefault(child, concept_label(segs[i + 2]))
                        out.append(
                            (
                                parent,
                                child,
                                CandidateEvidence(
                                    "sub_resource",
                                    d.doc_id,
                                    d.title,
                                    paths=(segs[i + 1].strip("{}"),),
                                    fetch=f"{d.method} {d.path}",
                                    many=True,
                                    read=d.method == "GET",
                                ),
                            )
                        )
                        break
        return out

    def _field_hits(
        self, r: ResolvedBuild, scan: _Api, concepts: set[str]
    ) -> dict[str, list[tuple[str, str, str, str, bool, str]]]:
        """Field facts that may be evidence: nested containers, id fields, model refs."""
        build = r.build.build_id
        wanted: dict[str, list[tuple[str, str, str, str, bool, str]]] = defaultdict(list)
        for f in self._facts.list_facts(build):
            if f.kind is not FactKind.FIELD or f.location not in _BODY:
                continue
            owner = scan.owner.get(f.owner_id)
            if owner is None:
                continue
            segs = f.name.split(".")
            sub = f.owner_id in scan.sub  # its top level is the sub-collection, not the owner
            current = owner  # the innermost enclosing concept (holder of nested concepts)
            inner = owner  # the innermost enclosing container (holder of an id field)
            for depth, seg in enumerate(segs[:-1]):
                key = _segment_key(seg)
                if _wrapper(seg):
                    break  # under _links / previous / ...: links, not nesting
                if not key or key in NOISE:
                    continue
                if key != inner:
                    inner = key
                    scan.names.setdefault(key, concept_label(seg.replace("[]", "")))
                if key in concepts and key != current and not (sub and current == owner):
                    path = ".".join(segs[: depth + 1])
                    wanted[f.owner_id].append(
                        ("nested", current, key, path, seg.endswith("[]"), f.name)
                    )
                    current = key
            leaf = segs[-1].replace("[]", "")
            m = _ID.match(leaf)
            if inner == owner and sub:
                pass  # a sub-collection's own ids
            elif m or leaf == "parent_id":
                stem = concept_key(m.group("stem")) if m else ""
                plural = bool(m and m.group("plural") == "ids")
                wanted[f.owner_id].append(("id_field", inner, stem, f.name, plural, f.name))
            ftype = concept_key((f.type or "").replace("array", "").strip("<>[] "))
            if ftype in concepts and ftype != current:
                wanted[f.owner_id].append(
                    (
                        "model_ref",
                        current,
                        ftype,
                        f.name,
                        "[]" in f.name or "array" in (f.type or ""),
                        f.name,
                    )
                )
        return wanted

    def _field_evidence(
        self,
        r: ResolvedBuild,
        scan: _Api,
        concepts: set[str],
        wanted: dict[str, list[tuple[str, str, str, str, bool, str]]],
    ) -> list[tuple[str, str, CandidateEvidence]]:
        """Read the descriptions; keep id fields only when the description names the target."""
        build = r.build.build_id

        def label(key: str) -> str:
            return scan.names.get(key) or concept_label(key)

        out: list[tuple[str, str, CandidateEvidence]] = []
        seen: set[tuple[str, str, str, str, str]] = set()  # per document: ranked later
        for doc_id, items in wanted.items():
            doc = self._documents.get_document(build, doc_id)
            if doc is None:
                continue
            specs = {s.name: s for s in doc.fields}
            for kind, holder, target, path, many, fname in items:
                spec = specs.get(fname)
                desc = (spec.description or "").strip() if spec else ""
                if kind == "id_field":
                    # line_items[].product_id: the item model line_items references holds it.
                    container = fname.rsplit(".", 1)[0].removesuffix("[]") if "." in fname else ""
                    item = (
                        _referenced_concept(doc.fields, container, concepts) if container else None
                    )
                    if item and container:
                        _record_merge(scan, scan.owner.get(doc_id), container, item)
                    owner_of = item or holder  # the item model holds the id
                    # The description must NAME the target (the field name alone proves nothing).
                    targets = [target] if target in concepts else []
                    if not targets and fname.endswith("parent_id"):  # any concept the text names
                        targets = [c for c in concepts if desc and _names_concept(
                            desc, c, label(c))]  # fmt: skip
                    for t in targets:
                        if t == owner_of or not desc or not _names_concept(desc, t, label(t)):
                            continue
                        if (kind, t, holder, path, doc_id) in seen:
                            continue
                        seen.add((kind, t, holder, path, doc_id))
                        out.append(
                            (
                                t,
                                holder,
                                CandidateEvidence(
                                    kind,
                                    doc_id,
                                    desc,
                                    (path,),
                                    many=many,
                                    read=_read(spec, doc.method),
                                ),
                            )
                        )
                    continue
                child = target
                item = _referenced_concept(doc.fields, path, concepts)
                if item:
                    _record_merge(scan, scan.owner.get(doc_id), path, item)
                if child == holder:
                    continue
                spec_of = specs.get(path)
                quote = (
                    ((spec_of.description or "").strip() if spec_of else "") or desc or doc.title
                )
                if (kind, holder, child, path, doc_id) in seen:
                    continue
                seen.add((kind, holder, child, path, doc_id))
                out.append(
                    (
                        holder,
                        child,
                        CandidateEvidence(
                            kind,
                            doc_id,
                            quote,
                            (path,),
                            many=many,
                            read=_read(spec_of or spec, doc.method),
                        ),
                    )
                )
        return out

    def execute(
        self, apis: list[str], concept: str, limit: int = 24, offset: int = 0
    ) -> RelatedConcepts:
        resolved = resolve_apis(self._resolver, apis)
        key = concept_key(concept)
        if not key:
            raise ModelInputError("concept is empty")
        cands, aliases, labels = self.candidates(resolved)
        by_other: dict[str, list[RelationCandidate]] = defaultdict(list)
        for c in cands:
            if c.parent == key:
                by_other[c.child].append(c)
            elif c.child == key:
                by_other[c.parent].append(c)
        related: list[RelatedConcept] = []
        known = set(labels) | {c.parent for c in cands} | {c.child for c in cands}
        last_words = {v.split()[-1].lower() for v in labels.values() if " " in v}
        named: dict[str, RelatedConcept] = {}
        for other, cs in by_other.items():
            name = tidy_concept(
                labels.get(other, concept_label(other)), known - {other}, last_words
            )
            if name is None:
                continue
            kinds = {
                r.api.api_id.value: tuple(
                    sorted({k for c in cs for k in c.kinds(r.api.api_id.value)}, key=KINDS.index)
                )
                for r in resolved
            }
            item = RelatedConcept(
                key=other,
                name=name,
                candidates=tuple(cs),
                kinds=kinds,
                evidence=sum(len(es) for c in cs for es in c.sources.values()),
            )
            twin = named.get(name.lower())
            if twin is None:
                named[name.lower()] = item
                related.append(item)
            else:  # two keys, one name ("Customer Customer Address"): one entry
                merged = RelatedConcept(
                    key=twin.key,
                    name=twin.name,
                    candidates=twin.candidates + item.candidates,
                    kinds={
                        a: tuple(dict.fromkeys(twin.kinds[a] + item.kinds[a])) for a in twin.kinds
                    },
                    evidence=twin.evidence + item.evidence,
                )
                related[related.index(twin)] = merged
                named[name.lower()] = merged
        related.sort(key=lambda r: (-sum(bool(v) for v in r.kinds.values()), -r.evidence, r.key))
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        mine = tuple(a for a in aliases if a.parent == key or key in a.names.values())
        return RelatedConcepts(
            apis=resolved,
            concept=key,
            name=labels.get(key, concept_label(key)),
            related=tuple(related[offset : offset + limit]),
            total=len(related),
            aliases=mine,
            labels=labels,
            limit=limit,
            offset=offset,
        )
