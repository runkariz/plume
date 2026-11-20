"""Lookups into a session's pinned builds for draft validation (``domain.models.validation``),
cached for one validation: a large draft cites the same documents, paths and endpoints many
times, and each lookup would be a database round trip."""

from collections.abc import Sequence

from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.search_index import FactQuery
from plume.domain.knowledge.call_check import path_matches, specificity
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.models.validation import Oracle
from plume.domain.shared.ids import BuildId


def own_specs(fields: Sequence[FieldSpec], path: str) -> list[FieldSpec]:
    """The field a path names in a document: its exact name ([] ignored), else longer names
    ending with it (checkoutForm.fulfillment.status for fulfillment.status); never a shorter
    or another path with the same last segment (region.region is not region; lineItems[]
    .quantity is not reconciliation.quantity)."""
    wanted = path.lower().replace("[]", "")
    exact = [f for f in fields if f.name.lower().replace("[]", "") == wanted]
    if exact:
        return exact
    return [f for f in fields if f.name.lower().replace("[]", "").endswith("." + wanted)]


class PinnedLookups:
    def __init__(self, builds: dict[str, BuildId], facts: FactQuery, documents: DocumentRepo):
        self._builds = builds
        self._facts = facts
        self._documents = documents
        self._docs: dict[tuple[str, str], Document | None] = {}
        self._texts: dict[tuple[str, str], str | None] = {}
        self._known: dict[str, set[str]] = {}
        self._names: dict[str, list[str]] = {}
        self._endpoints: dict[str, list[tuple[str, str, str]]] = {}  # (method, path, owner)
        self._children: dict[str, dict[str, list[str]]] = {}  # api -> field -> direct subs
        self._types: dict[str, dict[str, list[tuple[str, str | None]]]] = {}

    def oracle(self) -> Oracle:
        return Oracle(
            self.doc_text,
            self.field_exists,
            self.endpoint_exists,
            self.write_only,
            self.field_texts,
            self.fetch_fields,
            self.path_shape,
            self.path_enum,
            self.call_fields,
        )

    def doc(self, api: str, doc_id: str) -> Document | None:
        if (api, doc_id) not in self._docs:
            self._docs[(api, doc_id)] = self._documents.get_document(self._builds[api], doc_id)
        return self._docs[(api, doc_id)]

    def doc_text(self, api: str, doc_id: str) -> str | None:
        if (api, doc_id) not in self._texts:
            d = self.doc(api, doc_id)
            self._texts[(api, doc_id)] = (
                None
                if d is None
                else f"{d.title}\n{d.text}\n{' '.join(f.description or '' for f in d.fields)}"
            )
        return self._texts[(api, doc_id)]

    def write_only(self, api: str, doc_id: str) -> bool:
        d = self.doc(api, doc_id)
        return d is not None and d.kind is DocumentKind.ENDPOINT and (d.method or "GET") != "GET"

    def field_texts(self, api: str, doc_id: str, path: str) -> tuple[str, ...] | None:
        """The field's description and its line(s) in the document text; None when the
        document does not list the field."""
        d = self.doc(api, doc_id)
        if d is None:
            return None
        specs = own_specs(d.fields, path)
        if not specs:
            return None
        lines = [ln for f in specs for ln in d.text.splitlines() if f"`{f.name}`" in ln]
        return tuple(t for t in (*(f.description or "" for f in specs), *lines) if t)

    def field_exists(self, api: str, path: str) -> bool:
        """Same rule as FactQuery.find (exact name or a ".name" suffix, case-insensitive), from
        one query per API instead of one scan per path."""
        if api not in self._known:
            names = self._known[api] = set()
            self._names[api] = list(self._facts.field_names(self._builds[api]))
            for name in self._names[api]:
                parts = name.lower().split(".")
                names.update(".".join(parts[i:]) for i in range(len(parts)))
        return path.lower() in self._known[api]

    def _child_index(self, api: str) -> dict[str, list[str]]:
        """field name -> its direct sub-field names (``line_items[]`` and ``line_items`` both
        key the items' fields), built once per API in one pass over the field names: a large
        build (Shopware, ~560k field facts) must not be scanned per citation."""
        if api not in self._children:
            self.field_exists(api, "")
            index: dict[str, dict[str, None]] = {}
            for name in self._names[api]:
                parent, dot, leaf = name.rpartition(".")
                if dot and leaf:
                    index.setdefault(parent, {})[leaf] = None
                    if parent.endswith("[]"):
                        index.setdefault(parent[:-2], {})[leaf] = None
            self._children[api] = {k: list(v) for k, v in index.items()}
        return self._children[api]

    def _type_index(self, api: str) -> dict[str, list[tuple[str, str | None]]]:
        """last name segment (lower case) -> [(field name, type)], one query per API."""
        if api not in self._types:
            index: dict[str, list[tuple[str, str | None]]] = {}
            for name, ftype in self._facts.field_types(self._builds[api]):
                leaf = name.rsplit(".", 1)[-1].replace("[]", "").lower()
                index.setdefault(leaf, []).append((name, ftype))
            self._types[api] = index
        return self._types[api]

    def path_shape(self, api: str, path: str) -> tuple[frozenset[str], tuple[str, ...]]:
        """The types the API states for the field (the same name rule as FactQuery.find: the
        name or a dotted suffix of it), and its direct sub-fields (from every listed field,
        not the paged evidence). In memory, per API: no query per citation."""
        children = self._child_index(api)
        wanted = path.lower()
        leaf = wanted.rsplit(".", 1)[-1].replace("[]", "")
        matches = [
            (name, ftype)
            for name, ftype in self._type_index(api).get(leaf, ())
            if name.lower() == wanted or name.lower().endswith("." + wanted)
        ]
        types = frozenset(t for _, t in matches if t)
        subs: dict[str, None] = {}
        for full in {name for name, _ in matches}:
            for sub in children.get(full, ()):
                subs[sub] = None
        return types, tuple(subs)

    def path_enum(self, api: str, path: str, doc_ids: tuple[str, ...]) -> tuple[str, ...] | None:
        """The enum values the cited documents state for the field itself: a field whose name
        IS the path, or ends with it (checkoutForm.fulfillment.status for fulfillment.status),
        never a shorter one (status is another field than fulfillment.status). None: none
        states one."""
        values: dict[str, None] = {}
        for doc_id in doc_ids:
            d = self.doc(api, doc_id)
            for spec in own_specs(d.fields, path) if d is not None else ():
                for v in spec.constraint_dict.get("enum") or ():
                    values[str(v)] = None
        return tuple(values) or None

    def _endpoint_rows(self, api: str) -> list[tuple[str, str, str]]:
        if api not in self._endpoints:
            self._endpoints[api] = [
                (m, p, f.owner_id)
                for f in self._facts.endpoints(self._builds[api])
                for m, _, p in [f.name.partition(" ")]
            ]
        return self._endpoints[api]

    def _owners(self, api: str, call: str) -> list[str]:
        """The endpoint(s) a call names: the exact template, else the most specific templates
        that match (orders/count.json is not orders/{order_id}.json)."""
        method, _, path = call.strip().partition(" ")
        path = path.strip()
        rows = [(p, owner) for m, p, owner in self._endpoint_rows(api) if m == method.upper()]
        exact = [owner for p, owner in rows if p == path]
        if exact:
            return exact
        matching = [(p, owner) for p, owner in rows if path_matches(p, path)]
        best = max((specificity(p) for p, _ in matching), default=0)
        return [owner for p, owner in matching if specificity(p) == best]

    def endpoint_exists(self, api: str, call: str) -> bool:
        return bool(self._owners(api, call))

    def call_fields(self, api: str, call: str) -> frozenset[str] | None:
        """Every field name of the endpoint ``call`` names (request and response)."""
        names = {
            spec.name
            for owner in self._owners(api, call)
            if (d := self.doc(api, owner)) is not None
            for spec in d.fields
        }
        return frozenset(names) or None

    def fetch_fields(self, api: str, call: str) -> frozenset[str] | None:
        """The response field names of the endpoint ``call`` names (None: none listed)."""
        names = {
            spec.name
            for owner in self._owners(api, call)
            if (d := self.doc(api, owner)) is not None
            for spec in d.fields
            if spec.location is FieldLocation.RESPONSE
        }
        return frozenset(names) or None
