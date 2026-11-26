"""The same behaviour from the fakes and from Postgres."""

from datetime import UTC, datetime, timedelta

import pytest

from plume.domain.knowledge.api import ApiId, ApiInfo, Category
from plume.domain.knowledge.build import Build, BuildSpec
from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.knowledge.fact import facts_of
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.hashing import content_hash
from tests.contract.conftest import Store

T0 = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
API = ApiId("acme")
INFO = ApiInfo(
    api_id=API,
    name="Acme",
    summary="Acme API",
    doc_link="https://acme.test/docs",
    category=Category("e-commerce", "shop", 0.9, 38),
    versions=("v1",),
)
SPEC = BuildSpec("sha256:pkg", "1", "fake-embed-v1", 4, "packages/acme", "r_1")
DOC = Document(
    doc_id="endpoint:GET~/orders",
    kind=DocumentKind.ENDPOINT,
    title="List orders",
    text="# List orders\n\nReturns orders.",
    source_url="https://acme.test/orders",
    anchor="#list",
    resource="Order",
    method="GET",
    path="/orders",
    deprecated=True,
    complete=False,
    fields=(FieldSpec("limit", FieldLocation.QUERY, "integer", True, "Page size", "p#/x"),),
    scopes=("read_orders",),
    source_id="get-orders",
)
GUIDE = Document(doc_id="guide:auth", kind=DocumentKind.GUIDE, title="Auth", text="Use a key.")


def _chunk(doc: Document, text: str, ordinal: int = 0) -> Chunk:
    return Chunk(f"{doc.doc_id}#{ordinal}", doc.doc_id, ordinal, doc.title, text)


DIMS = 768


def _vec(*xs: float) -> tuple[float, ...]:
    """A 768-dim vector padded with zeros; values are exact in half precision (halfvec)."""
    return tuple(xs) + (0.0,) * (DIMS - len(xs))


def _draft(store: Store, created: datetime = T0, spec: BuildSpec = SPEC) -> Build:
    store.apis.upsert(INFO)
    build = Build.start(API, created, spec=spec)
    store.builds.save(build)
    return build


def test_api_upsert_get_list(store: Store) -> None:
    store.apis.upsert(INFO)
    assert store.apis.get(API) == INFO
    store.apis.upsert(ApiInfo(api_id=API, name="Acme 2"))
    assert store.apis.get(API) == ApiInfo(api_id=API, name="Acme 2")
    assert store.apis.get(ApiId("nope")) is None
    store.apis.upsert(ApiInfo(api_id=ApiId("aaa"), name="A"))
    assert [a.api_id.value for a in store.apis.list()] == ["aaa", "acme"]


def test_build_round_trip_and_seal(store: Store) -> None:
    draft = _draft(store).with_item("x#0", content_hash("x")).with_item("y#0", content_hash("y"))
    store.builds.save(draft)
    loaded = store.builds.get(draft.build_id)
    assert loaded == draft
    assert loaded is not None
    assert loaded.spec == SPEC
    sealed = draft.seal(T0 + timedelta(minutes=1))
    store.builds.save(sealed)
    assert store.builds.get(sealed.build_id) == sealed
    store.builds.save(sealed)  # idempotent
    with pytest.raises(ValueError, match="sealed"):
        store.builds.save(draft)  # a sealed build never goes back to draft


def test_builds_listed_newest_first(store: Store) -> None:
    old = _draft(store, T0)
    new = _draft(store, T0 + timedelta(hours=1), BuildSpec("sha256:other", "1", "m", 4))
    assert [b.build_id for b in store.builds.list(API)] == [new.build_id, old.build_id]
    assert store.builds.list(ApiId("nobody")) == []


def test_tags_create_move_list(store: Store) -> None:
    a = _draft(store).with_item("x#0", content_hash("x")).seal(T0 + timedelta(seconds=1))
    b = (
        _draft(store, T0, BuildSpec("sha256:b", "1", "m", 4))
        .with_item("x#0", content_hash("y"))
        .seal(T0 + timedelta(seconds=2))
    )
    store.builds.save(a)
    store.builds.save(b)
    latest = Tag.point(TagName("latest"), a)
    store.tags.set(latest)
    assert store.tags.get(API, TagName("latest")) == latest
    store.tags.set(latest.move_to(b))
    assert store.tags.get(API, TagName("latest")).build_id == b.build_id  # type: ignore[union-attr]
    store.tags.set(Tag.point(TagName("stable"), a))
    assert [t.name.value for t in store.tags.list(API)] == ["latest", "stable"]
    assert store.tags.get(API, TagName("nope")) is None


def test_documents_round_trip_and_upsert(store: Store) -> None:
    build = _draft(store)
    store.documents.add_documents(build.build_id, [GUIDE, DOC])
    assert store.documents.list_documents(build.build_id) == [DOC, GUIDE]
    assert store.documents.get_document(build.build_id, DOC.doc_id) == DOC
    changed = Document(doc_id="guide:auth", kind=DocumentKind.GUIDE, title="Auth", text="v2")
    store.documents.add_documents(build.build_id, [changed])
    assert store.documents.get_document(build.build_id, "guide:auth") == changed
    assert store.documents.get_document(build.build_id, "guide:none") is None


def test_chunks_vectors_and_missing(store: Store) -> None:
    build = _draft(store)
    store.documents.add_documents(build.build_id, [DOC, GUIDE])
    c1, c2 = _chunk(DOC, "orders"), _chunk(GUIDE, "key")
    store.documents.replace_chunks(build.build_id, [c2, c1])
    assert store.documents.list_chunks(build.build_id) == [c1, c2]
    assert store.vectors.missing(build.build_id) == [c1.chunk_id, c2.chunk_id]

    store.vectors.set_vectors(build.build_id, {c1.chunk_id: _vec(1, 0, 0, 0)})
    assert store.vectors.missing(build.build_id) == [c2.chunk_id]

    # Same embed text keeps the vector; changed text drops it; removed chunks go away.
    store.documents.replace_chunks(build.build_id, [c1, _chunk(GUIDE, "key v2")])
    assert store.vectors.missing(build.build_id) == [c2.chunk_id]
    store.documents.replace_chunks(build.build_id, [_chunk(DOC, "orders v2")])
    assert store.vectors.missing(build.build_id) == [c1.chunk_id]
    assert len(store.documents.list_chunks(build.build_id)) == 1


def test_embed_cache(store: Store) -> None:
    v = _vec(0.5, 0.5, 0.5, 0.5)
    store.vectors.cache("m", DIMS, {"h1": v})
    store.vectors.cache("m", DIMS, {"h1": _vec(1, 0, 0, 0)})  # first write wins
    assert store.vectors.cached("m", DIMS, ["h1", "h2"]) == {"h1": v}
    assert store.vectors.cached("other", DIMS, ["h1"]) == {}
    assert store.vectors.cached("m", DIMS, []) == {}


def test_facts_replace_and_list(store: Store) -> None:
    build = _draft(store)
    facts = facts_of(DOC)
    store.facts.replace_facts(build.build_id, facts)
    assert store.facts.list_facts(build.build_id) == sorted(facts, key=lambda f: f.fact_id)
    store.facts.replace_facts(build.build_id, facts[:1])
    assert store.facts.list_facts(build.build_id) == facts[:1]


def test_documents_keep_raw_and_tags(store: Store) -> None:
    from dataclasses import replace  # noqa: PLC0415

    build = _draft(store)
    raw = {
        "endpointId": "get-orders",
        "tags": [{"kind": "category", "name": "orders"}],
        "nested": {"a": [1, 2, {"b": None}]},
    }
    doc = replace(DOC, tags=("v1", "orders"), raw=raw)
    store.documents.add_documents(build.build_id, [doc])
    got = store.documents.get_document(build.build_id, DOC.doc_id)
    assert got == doc
    assert got is not None
    assert got.raw == raw
    assert got.tags == ("v1", "orders")
    items, total = store.search.browse(build.build_id, (), None, 10, 0, tag="orders")
    assert (total, items[0].tags) == (1, ("v1", "orders"))
    assert store.search.browse(build.build_id, (), None, 10, 0, tag="nope")[1] == 0


def test_documents_by_source_ids(store: Store) -> None:
    from dataclasses import replace  # noqa: PLC0415

    build = _draft(store)
    doc = replace(DOC, source_id="get-orders-2026-10")
    store.documents.add_documents(build.build_id, [doc])
    found = store.documents.by_source_ids(
        build.build_id, DOC.kind, ["get-orders-2026-10", "missing"]
    )
    assert list(found) == ["get-orders-2026-10"]
    assert found["get-orders-2026-10"].doc_id == DOC.doc_id
    other = next(k for k in DocumentKind if k is not DOC.kind)
    assert store.documents.by_source_ids(build.build_id, other, ["get-orders-2026-10"]) == {}
    assert store.documents.by_source_ids(build.build_id, DOC.kind, []) == {}


def test_operation_ids(store: Store) -> None:
    """(specOperationId, endpoint doc id) for endpoints with a string one, by doc id."""
    from dataclasses import replace  # noqa: PLC0415

    build = _draft(store)
    a = replace(DOC, doc_id="endpoint:GET~/b", raw={"specOperationId": "A02"})
    b = replace(DOC, doc_id="endpoint:GET~/a", raw={"specOperationId": "OR11"})
    none = replace(DOC, doc_id="endpoint:GET~/c", raw={"specOperationId": 7})
    guide = replace(GUIDE, raw={"specOperationId": "X1"})
    store.documents.add_documents(build.build_id, [a, b, none, guide])
    assert store.documents.operation_ids(build.build_id) == [
        ("OR11", "endpoint:GET~/a"), ("A02", "endpoint:GET~/b")]  # fmt: skip


def test_model_users(store: Store) -> None:
    """Endpoints/triggers with a field whose type is the model, with the field locations."""
    from dataclasses import replace  # noqa: PLC0415

    build = _draft(store)
    money = "model:money"
    uses = replace(DOC, fields=(
        FieldSpec("total", FieldLocation.RESPONSE, "object", model_id=money),
        FieldSpec("lines[].price", FieldLocation.RESPONSE, "object", model_id=money),
        FieldSpec("refund", FieldLocation.BODY, "object", model_id=money),
        FieldSpec("limit", FieldLocation.QUERY, "integer"),
    ))  # fmt: skip
    other = replace(DOC, doc_id="endpoint:GET~/carts", fields=(
        FieldSpec("x", FieldLocation.RESPONSE, "object", model_id="model:moneybag"),))  # fmt: skip
    model = Document(doc_id=money, kind=DocumentKind.MODEL, title="Money", text="# Money",
                     fields=(FieldSpec("self", FieldLocation.MODEL, model_id=money),))  # fmt: skip
    store.documents.add_documents(build.build_id, [uses, other, model, GUIDE])
    assert store.documents.model_users(build.build_id, money) == [
        (DOC.doc_id, ("body", "response"))]  # fmt: skip
    assert store.documents.model_users(build.build_id, "model:none") == []


def test_assets(store: Store, request: pytest.FixtureRequest) -> None:
    from plume.domain.knowledge.asset import Asset  # noqa: PLC0415
    from plume.infrastructure.db.repos.asset_repo import PostgresAssetRepo  # noqa: PLC0415
    from tests.fakes.knowledge import InMemoryAssetRepo  # noqa: PLC0415

    repo = (
        InMemoryAssetRepo()
        if store.kind == "fake"
        else PostgresAssetRepo(request.getfixturevalue("clean_engine"))
    )
    build = _draft(store)
    icon = Asset("icon", "image/png", b"\x89PNG\r\n\x1a\nxyz", "connector/icon.png")
    repo.put(build.build_id, [icon])
    assert repo.get(build.build_id, "icon") == icon
    assert repo.get(build.build_id, "other") is None
    assert repo.has(build.build_id, "icon") is True
    assert repo.has(build.build_id, "other") is False
    assert repo.list(build.build_id) == [icon]
    repo.put(build.build_id, [Asset("icon", "image/svg+xml", b"<svg/>", "connector/icon.svg")])
    assert repo.get(build.build_id, "icon").content_type == "image/svg+xml"  # type: ignore[union-attr]
