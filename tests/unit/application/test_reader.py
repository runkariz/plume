from pathlib import Path

import pytest

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.reader.use_cases import ReaderInputError
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack


@pytest.fixture
def shop(packages: Path) -> FakeStack:
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(packages / "shopify-mini"))
    stack.load(str(packages / "test-catalog"))
    return stack


def test_overviews(shop: FakeStack) -> None:
    apis = {o.info.api_id.value: o for o in shop.overviews().execute()}
    assert set(apis) == {"shopify", "test-catalog-api"}
    o = apis["shopify"]
    assert o.ref is not None
    assert o.ref.tag == "latest"
    assert o.counts["endpoint"] == 7
    assert o.counts["model"] == 4
    assert o.counts["chunks"] >= 15
    assert o.tags == ("latest",)
    assert o.embed_model == "fake-words-v1"


def test_unknown_api_tag_or_build(shop: FakeStack) -> None:
    with pytest.raises(NotFoundError):
        shop.overviews().one("nope")
    with pytest.raises(NotFoundError):
        shop.overviews().one("shopify", "stable")
    with pytest.raises(NotFoundError):
        shop.overviews().one("shopify", "b-" + "0" * 32)
    with pytest.raises(NotFoundError):
        shop.overviews().one("Bad Id")


def test_pin_by_build_id(shop: FakeStack) -> None:
    latest = shop.overviews().one("shopify")
    assert latest.ref is not None
    pinned = shop.overviews().one("shopify", latest.ref.build)
    assert pinned.ref is not None
    assert pinned.ref.build == latest.ref.build
    assert pinned.ref.tag is None


def test_browse(shop: FakeStack) -> None:
    _, items, total = shop.browse().execute("shopify", "endpoint", limit=3)
    assert total == 7
    assert len(items) == 3
    assert all(i.kind.value == "endpoint" for i in items)
    _, found, n = shop.browse().execute("shopify", None, "fulfillment")
    assert n == len(found) >= 2
    with pytest.raises(ReaderInputError):
        shop.browse().execute("shopify", "widget")
    with pytest.raises(ReaderInputError):
        shop.browse().execute("shopify", limit=0)


@pytest.mark.parametrize("mode", ["hybrid", "dense", "text"])
def test_search_ranks_the_right_endpoint_first(shop: FakeStack, mode: str) -> None:
    r = shop.search().execute("shopify", "assigned fulfillment orders", mode, top_k=5)  # type: ignore[arg-type]
    assert r.hits[0].doc_id == "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"
    assert r.hits[0].subtitle.startswith("GET /admin/api/{version}/")
    assert r.ref.api == "shopify"
    steps = [t.label for t in r.trace]
    assert ("embed query" in steps) == (mode != "text")
    assert ("full-text search" in steps) == (mode != "dense")


def test_search_hit_fields_and_kind_filter(shop: FakeStack) -> None:
    r = shop.search().execute("shopify", "customer address", kind="model", top_k=3)
    assert r.hits
    assert all(h.kind.value == "model" for h in r.hits)
    hit = r.hits[0]
    assert hit.fused > 0
    assert hit.snippet
    assert len({h.doc_id for h in r.hits}) == len(r.hits)  # one hit per document


def test_search_validation(shop: FakeStack) -> None:
    with pytest.raises(ReaderInputError):
        shop.search().execute("shopify", "  ")
    with pytest.raises(ReaderInputError):
        shop.search().execute("shopify", "x", top_k=0)
    with pytest.raises(ReaderInputError):
        shop.search().execute("shopify", "x", mode="fuzzy")  # type: ignore[arg-type]


def test_search_refuses_a_different_embedder(packages: Path) -> None:
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(packages / "test-catalog"))
    other = FakeStack(
        apis=stack.apis, builds=stack.builds, tags=stack.tags, documents=stack.documents
    )
    with pytest.raises(ApplicationError, match="embedded with"):
        other.search().execute("test-catalog-api", "orders")
    assert other.search().execute("test-catalog-api", "orders", mode="text").hits


def test_get_document(shop: FakeStack) -> None:
    r = shop.get_document().execute("shopify", "model:customer")
    assert r.document.title == "Customer"
    assert r.citation.doc_id == "model:customer"
    assert r.citation.source_url
    with pytest.raises(NotFoundError):
        shop.get_document().execute("shopify", "model:nope")


def test_find_fact_present_with_evidence(shop: FakeStack) -> None:
    r = shop.find_fact().execute("shopify", "read_assigned_fulfillment_orders", kind="scope")
    assert r.found
    owners = {m.owner_id for m in r.matches}
    assert "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json" in owners
    r = shop.find_fact().execute("shopify", "since_id", location="query")
    assert r.found
    m = r.matches[0]
    assert m.citation.anchor is not None
    assert m.citation.anchor.endswith("/properties/since_id")
    assert m.owner_title == "List products"


def test_find_fact_suffix_match(shop: FakeStack) -> None:
    r = shop.find_fact().execute("shopify", "sku")
    assert r.found
    assert all(m.name == "sku" or m.name.endswith(".sku") for m in r.matches)


def test_absent_and_complete(packages: Path) -> None:
    stack = FakeStack()
    stack.load(str(packages / "test-catalog"))
    r = stack.find_fact().execute("test-catalog-api", "loyalty_points")
    assert not r.found
    assert r.complete
    assert r.checked == {"endpoints": 2, "models": 3}
    assert "Not documented in build" in r.wording
    assert "never 'does not exist'" in r.wording


def test_absent_but_incomplete(shop: FakeStack) -> None:
    r = shop.find_fact().execute("shopify", "loyalty_points", owner="model:customer")
    assert not r.found
    assert not r.complete
    assert r.incomplete_sources == ("model:customer",)
    assert "NOT proven" in r.wording
    r = shop.find_fact().execute("shopify", "loyalty_points", owner="model:address")
    assert r.complete


def test_find_fact_text_mentions_and_errors(shop: FakeStack) -> None:
    r = shop.find_fact().execute("shopify", "Retry-After")
    assert not r.found
    assert r.text_mentions
    assert "appears in prose" in r.wording
    with pytest.raises(NotFoundError):
        shop.find_fact().execute("shopify", "x", owner="model:nope")
    with pytest.raises(ReaderInputError):
        shop.find_fact().execute("shopify", "x", kind="widget")
    with pytest.raises(ReaderInputError):
        shop.find_fact().execute("shopify", " ")


def test_check_call(shop: FakeStack) -> None:
    ok = shop.check_call().execute(
        "shopify", "get", "/admin/api/2026-10/products/632910392.json", ["fields"]
    )
    assert ok.verdict == "documented"
    assert ok.matched_path == "/admin/api/{version}/products/{product_id}.json"
    assert ok.params[0].where == "query"
    assert ok.citation is not None

    bad_param = shop.check_call().execute(
        "shopify", "GET", "/admin/api/latest/products.json", ["color"]
    )
    assert bad_param.verdict == "not_documented"
    assert bad_param.matched_id is not None
    assert not bad_param.params[0].found

    missing = shop.check_call().execute("shopify", "PATCH", "/admin/api/latest/products.json")
    assert missing.verdict == "not_documented"
    assert missing.matched_id is None
    assert missing.checked["endpoints"] == 7

    with pytest.raises(ReaderInputError):
        shop.check_call().execute("shopify", "FETCH", "/x")
    with pytest.raises(ReaderInputError):
        shop.check_call().execute("shopify", "GET", " ")
