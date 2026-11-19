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
