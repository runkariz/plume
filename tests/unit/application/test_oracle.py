"""PinnedLookups: a call names the most specific endpoint (count.json is not {id}.json)."""

from types import SimpleNamespace
from typing import Any

from plume.application.models.oracle import PinnedLookups
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.shared.ids import BuildId

DOCS = {
    "e:count": Document(doc_id="endpoint:GET~/orders/count.json", kind=DocumentKind.ENDPOINT,
                        title="count", text="t",
                        fields=(FieldSpec("count", FieldLocation.RESPONSE, "integer"),)),
    "e:one": Document(doc_id="endpoint:GET~/orders/{id}.json", kind=DocumentKind.ENDPOINT,
                      title="one", text="t",
                      fields=(FieldSpec("order.id", FieldLocation.RESPONSE, "integer"),)),
}  # fmt: skip


def test_the_most_specific_endpoint_answers() -> None:
    facts = SimpleNamespace(
        endpoints=lambda _b: [
            SimpleNamespace(name="GET /orders/count.json", owner_id="e:count"),
            SimpleNamespace(name="GET /orders/{id}.json", owner_id="e:one"),
        ]
    )
    documents = SimpleNamespace(get_document=lambda _b, doc_id: DOCS.get(doc_id))
    lookups = PinnedLookups({"a": BuildId("b-" + "0" * 32)}, facts, documents)
    assert lookups.fetch_fields("a", "GET /orders/count.json") == frozenset({"count"})
    assert lookups.fetch_fields("a", "GET /orders/42.json") == frozenset({"order.id"})


def test_shape_lookups_stay_fast_on_a_large_build() -> None:
    """Shopware-sized builds (~560k field facts): sub-fields and types come from per-API
    indexes built once, never a scan or a query per citation (plume-l2 took 312 s for 2)."""
    import time  # noqa: PLC0415

    names = [f"entity{e}.field{f}" for e in range(2000) for f in range(100)]  # 200k fields
    names += [f"entity{e}" for e in range(2000)]
    types = [(n, "object" if "." not in n else "string") for n in names]
    calls = {"find": 0}

    def find(*_a: object, **_k: object) -> list[object]:
        calls["find"] += 1
        return []

    facts = SimpleNamespace(field_names=lambda _b: names, field_types=lambda _b: types,
                            find=find, endpoints=lambda _b: [])  # fmt: skip
    documents = SimpleNamespace(get_document=lambda _b, _d: None)
    lookups = PinnedLookups({"a": BuildId("b-" + "0" * 32)}, facts, documents)
    start = time.perf_counter()
    for e in range(50):
        types_found, subs = lookups.path_shape("a", f"entity{e}")
        assert types_found == frozenset({"object"})
        assert len(subs) == 100
    assert time.perf_counter() - start < 5  # index building included
    assert calls["find"] == 0


def test_enum_of_the_path_itself_not_a_same_named_field() -> None:
    """Allegro: checkoutform.status [BOUGHT, ...] and fulfillment.status [NEW, ...] differ."""
    from plume.domain.knowledge.document import FieldSpec as Spec  # noqa: PLC0415

    doc = Document(
        doc_id="model:checkoutform", kind=DocumentKind.MODEL, title="t", text="t",
        fields=(
            Spec("status", FieldLocation.MODEL, "string",
                 constraints='{"enum": ["BOUGHT", "FILLED_IN", "CANCELLED"]}'),
            Spec("fulfillment.status", FieldLocation.MODEL, "string",
                 constraints='{"enum": ["NEW", "PROCESSING", "SENT"]}'),
        ),
    )  # fmt: skip
    facts = SimpleNamespace(endpoints=lambda _b: [])
    documents = SimpleNamespace(get_document=lambda _b, _d: doc)
    lookups = PinnedLookups({"a": BuildId("b-" + "0" * 32)}, facts, documents)
    cited = ("model:checkoutform",)
    assert lookups.path_enum("a", "fulfillment.status", cited) == ("NEW", "PROCESSING", "SENT")
    assert lookups.path_enum("a", "status", cited) == ("BOUGHT", "FILLED_IN", "CANCELLED")


def _doc_with(*fields: tuple[str, str]) -> Document:
    from plume.domain.knowledge.document import FieldSpec as Spec  # noqa: PLC0415

    text = "\n".join(f"- `{n}` (string): {d}" for n, d in fields)
    specs = tuple(Spec(n, FieldLocation.MODEL, "string", description=d) for n, d in fields)
    return Document(doc_id="model:x", kind=DocumentKind.MODEL, title="t", text=text, fields=specs)


def _no_quote_codes(doc: Document, path: str) -> list[str]:
    from plume.domain.models.canonical_model import parse_draft  # noqa: PLC0415
    from plume.domain.models.validation import validate  # noqa: PLC0415

    lookups = PinnedLookups(
        {"a": BuildId("b-" + "0" * 32)},
        SimpleNamespace(
            field_names=lambda _b: [f.name for f in doc.fields],
            field_types=lambda _b: [(f.name, "string") for f in doc.fields],
            endpoints=lambda _b: [],
        ),
        SimpleNamespace(get_document=lambda _b, _d: doc),
    )  # fmt: skip
    ev = {"doc_id": "model:x", "noQuote": "the description is one word"}
    field = {"name": "f", "type": "string", "description": "d",
             "sources": {"a": {"paths": [path], "evidence": [ev]}}}  # fmt: skip
    draft = parse_draft({"name": "M", "description": "d", "fields": [field]})
    return [i.code for i in validate(draft, frozenset({"a"}), lookups.oracle())]


def test_no_quote_is_judged_by_the_exact_path_not_its_parent_or_a_namesake() -> None:
    """plume-l2 s-ecf4c80be7564cb1: Magento region.region "Region" was refused as noQuote
    because the parent `region` has a sentence; Allegro lineItems[].quantity because
    reconciliation.quantity has one."""
    magento = _doc_with(("region", "Region or state details for the address."),
                        ("region.region", "Region"))  # fmt: skip
    assert _no_quote_codes(magento, "region.region") == []
    assert _no_quote_codes(magento, "region") == ["NO_QUOTE_NOT_ALLOWED"]
    allegro = _doc_with(("reconciliation.quantity", "Quantity of reconciled items"),
                        ("lineItems[].quantity", "quantity"))  # fmt: skip
    assert _no_quote_codes(allegro, "lineItems[].quantity") == []
    assert _no_quote_codes(allegro, "reconciliation.quantity") == ["NO_QUOTE_NOT_ALLOWED"]


def _quoted_codes(doc: Document, path: str, quote: str) -> tuple[list[str], Any]:
    from plume.domain.models.canonical_model import (  # noqa: PLC0415
        name_only_as_no_quote,
        parse_draft,
    )
    from plume.domain.models.validation import validate  # noqa: PLC0415

    lookups = PinnedLookups(
        {"a": BuildId("b-" + "0" * 32)},
        SimpleNamespace(
            field_names=lambda _b: [f.name for f in doc.fields],
            field_types=lambda _b: [(f.name, "string") for f in doc.fields],
            endpoints=lambda _b: [],
        ),
        SimpleNamespace(get_document=lambda _b, _d: doc),
    )  # fmt: skip
    ev = {"doc_id": "model:x", "quote": quote}
    field = {"name": "number", "type": "string", "description": "d",
             "sources": {"a": {"paths": [path], "evidence": [ev]}}}  # fmt: skip
    draft = name_only_as_no_quote(parse_draft({"name": "M", "description": "d", "fields": [field]}))
    codes = [i.code for i in validate(draft, frozenset({"a"}), lookups.oracle())]
    return codes, draft.fields[0].sources[0][1].evidence[0]


def test_a_quote_that_only_restates_the_name_is_no_evidence() -> None:
    """JTL-Wawi: "The SalesOrder SalesOrderNumber" was accepted as a quote. It becomes a noQuote
    citation (not shown as evidenced); a real sentence elsewhere must be quoted instead."""
    jtl = _doc_with(("salesOrderNumber", "The SalesOrder SalesOrderNumber"))
    codes, ev = _quoted_codes(jtl, "salesOrderNumber", "The SalesOrder SalesOrderNumber")
    assert codes == []
    assert (ev.quote, ev.no_quote) == ("", "the description only restates the field name")
    richer = _doc_with(("salesOrderNumber", "The SalesOrder SalesOrderNumber. The number "
                        "printed on the invoice and the delivery note."))  # fmt: skip
    codes, _ = _quoted_codes(richer, "salesOrderNumber", "The SalesOrder SalesOrderNumber")
    assert codes == ["NO_QUOTE_NOT_ALLOWED"]
    # a vendor's short label is the field's whole description: it stays a quote
    label = _doc_with(("product_id", "Product ID."))
    codes, ev = _quoted_codes(label, "product_id", "Product ID.")
    assert ev.no_quote is None
