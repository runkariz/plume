"""PinnedLookups: a call names the most specific endpoint (count.json is not {id}.json)."""

from types import SimpleNamespace

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
