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
