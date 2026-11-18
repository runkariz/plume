"""SearchIndex / FactQuery: the same answers from the fakes and from Postgres."""

import pytest

from plume.domain.knowledge.api import ApiId, ApiInfo
from plume.domain.knowledge.build import Build, BuildSpec
from plume.domain.knowledge.chunk import chunk_document
from plume.domain.knowledge.document import (
    FIELDS_BOUNDED_KEY,
    Document,
    DocumentKind,
    FieldLocation,
    FieldSpec,
)
from plume.domain.knowledge.fact import FactKind, facts_of
from plume.domain.shared.ids import BuildId
from tests.contract.conftest import Store
from tests.contract.test_knowledge_store import T0, _vec

API = ApiId("acme")
ORDERS = Document(
    doc_id="endpoint:GET~/orders",
    kind=DocumentKind.ENDPOINT,
    title="List orders",
    text="Returns the orders of the shop, newest first.",
    resource="Order",
    method="GET",
    path="/orders",
    fields=(
        FieldSpec("limit", FieldLocation.QUERY, "integer", False, "Page size", "p#/limit"),
        FieldSpec("orders[].line_items[].sku", FieldLocation.RESPONSE, "string"),
    ),
    scopes=("read_orders",),
)
PRODUCT = Document(
    doc_id="model:product",
    kind=DocumentKind.MODEL,
    title="Product",
    text="A product sold in the catalog with variants and prices.",
    resource="Product",
    complete=False,
    fields=(FieldSpec("title", FieldLocation.MODEL, "string"),),
    raw={"type": "object", FIELDS_BOUNDED_KEY: 2},  # its field list stops at level 2
)
GUIDE = Document(
    doc_id="guide:rate-limits",
    kind=DocumentKind.GUIDE,
    title="Rate limits",
    text="Requests are limited by a leaky bucket per app per shop.",
)
ORDERED = ["endpoint:GET~/orders", "guide:rate-limits", "model:product"]
VECTORS = {
    "endpoint:GET~/orders#0": _vec(1.0),
    "model:product#0": _vec(0.0, 1.0),
    "guide:rate-limits#0": _vec(0.5, 0.5, 0.5, 0.5),
}


@pytest.fixture
def build(store: Store) -> BuildId:
    store.apis.upsert(ApiInfo(api_id=API, name="Acme"))
    b = Build.start(API, T0, spec=BuildSpec("sha256:s", "1", "m", 768))
    store.builds.save(b)
    docs = [ORDERS, PRODUCT, GUIDE]
    store.documents.add_documents(b.build_id, docs)
    store.documents.replace_chunks(b.build_id, [c for d in docs for c in chunk_document(d)])
    store.vectors.set_vectors(b.build_id, VECTORS)
    store.facts.replace_facts(b.build_id, [f for d in docs for f in facts_of(d)])
    return b.build_id


def test_dense_orders_by_cosine_and_filters_kind(store: Store, build: BuildId) -> None:
    hits = store.search.dense(build, _vec(0.9, 0.1), 3)
    assert [h.doc_id for h in hits] == [
        "endpoint:GET~/orders",
        "guide:rate-limits",
        "model:product",
    ]
    assert hits[0].score > hits[1].score > hits[2].score
    assert hits[0].kind is DocumentKind.ENDPOINT
    assert hits[0].title == "List orders"
    only = store.search.dense(build, _vec(0.9, 0.1), 3, [DocumentKind.MODEL])
    assert [h.doc_id for h in only] == ["model:product"]
    assert len(store.search.dense(build, _vec(1.0), 1)) == 1


def test_text_matches_words_and_filters(store: Store, build: BuildId) -> None:
    assert store.search.text(build, "leaky bucket", 5)[0].doc_id == "guide:rate-limits"
    assert store.search.text(build, "orders shop newest", 5)[0].doc_id == "endpoint:GET~/orders"
    assert store.search.text(build, "zebra quantum", 5) == []
    assert store.search.text(build, "catalog", 5, [DocumentKind.GUIDE]) == []


def test_browse_counts_summaries(store: Store, build: BuildId) -> None:
    items, total = store.search.browse(build)
    assert total == 3
    assert [i.doc_id for i in items] == [
        "endpoint:GET~/orders",
        "guide:rate-limits",
        "model:product",
    ]
    items, total = store.search.browse(build, [DocumentKind.ENDPOINT])
    assert (total, items[0].method, items[0].path) == (1, "GET", "/orders")
    items, total = store.search.browse(build, (), "RATE")
    assert [i.doc_id for i in items] == ["guide:rate-limits"]
    items, total = store.search.browse(build, (), None, 1, 1)
    assert [i.doc_id for i in items] == ["guide:rate-limits"]
    assert total == 3
    items, total = store.search.browse(build, (), None, 10, 10)
    assert (items, total) == ([], 3)
    assert store.search.browse(build, (), "100%_")[1] == 0
    assert store.search.counts(build) == {
        "endpoint": 1,
        "model": 1,
        "guide": 1,
        "chunks": 3,
        "model_shapes": 1,
        "model_names": 1,
    }
    s = store.search.summaries(build, ["model:product", "model:nope"])
    assert list(s) == ["model:product"]
    assert s["model:product"].resource == "Product"
    assert store.search.summaries(build, []) == {}


def test_fact_find_exact_suffix_and_filters(store: Store, build: BuildId) -> None:
    q = store.fact_query
    assert [f.name for f in q.find(build, "LIMIT")] == ["limit"]
    assert [f.name for f in q.find(build, "sku")] == ["orders[].line_items[].sku"]
    assert q.find(build, "ku") == []
    assert [f.kind for f in q.find(build, "read_orders")] == [FactKind.SCOPE]
    assert q.find(build, "limit", location=FieldLocation.BODY) == []
    assert q.find(build, "title", resource="product")[0].owner_id == "model:product"
    assert q.find(build, "title", owner_id="endpoint:GET~/orders") == []
    assert q.find(build, "title", kind=FactKind.ENDPOINT) == []
    assert q.find(build, "%") == []


def test_fact_owner_endpoints_incomplete(store: Store, build: BuildId) -> None:
    q = store.fact_query
    assert {f.name for f in q.for_owner(build, "endpoint:GET~/orders")} == {
        "GET /orders",
        "limit",
        "orders[].line_items[].sku",
        "read_orders",
    }
    assert [f.name for f in q.endpoints(build)] == ["GET /orders"]
    assert q.incomplete_owners(build) == ["model:product"]
    assert q.incomplete_owners(build, owner_id="endpoint:GET~/orders") == []
    assert q.incomplete_owners(build, resource="PRODUCT") == ["model:product"]
    assert q.bounded_owners(build) == {"model:product": 2}
    assert q.bounded_owners(build, owner_id="endpoint:GET~/orders") == {}
    assert q.bounded_owners(build, resource="product") == {"model:product": 2}
    assert q.bounded_owners(build, resource="Order") == {}


def test_model_shapes_and_names(store: Store) -> None:
    from dataclasses import replace  # noqa: PLC0415

    store.apis.upsert(ApiInfo(api_id=API, name="Acme"))
    b = Build.start(API, T0, spec=BuildSpec("sha256:m", "1", "m", 768))
    store.builds.save(b)
    base = Document(
        doc_id="model:a",
        kind=DocumentKind.MODEL,
        title="Address",
        text="t",
        resource="Address",
        shape="s1",
    )
    docs = [
        base,
        replace(base, doc_id="model:b", title="Shipping To / Address", shape="s2"),
        replace(base, doc_id="model:c", title="Billing / Address", shape="s1"),
        replace(base, doc_id="model:d", title="A01 response 200", resource=None, shape="s3"),
        replace(base, doc_id="model:e", title="Price", resource="Price", shape=None),
    ]
    store.documents.add_documents(b.build_id, docs)
    counts = store.search.counts(b.build_id)
    assert counts["model"] == 5
    assert counts["model_shapes"] == 4  # s1, s2, s3, and e (no shape) on its own
    assert counts["model_names"] == 2  # address, price (the root is not a name)
    assert store.documents.get_document(b.build_id, "model:b").shape == "s2"  # type: ignore[union-attr]
