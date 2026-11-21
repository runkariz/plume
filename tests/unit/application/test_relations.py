"""Relation candidates come only from documented evidence (docs/design/model-relations.md §2)."""

from pathlib import Path

import pytest

from plume.domain.knowledge.document import Document
from plume.domain.models.validation import quote_in
from plume.domain.shared.ids import BuildId
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.real_packages import real_packages


def _doc_text(d: Document) -> str:
    return " ".join([d.title, d.text] + [f.description or "" for f in d.fields])


def _assert_cited(stack: FakeStack, result: object) -> None:
    """Every quote is in the document it cites, in the build pinned for that API (the same
    check the model validation applies)."""
    builds = {r.api.api_id.value: r.build.build_id for r in result.apis}  # type: ignore[attr-defined]
    for rel in result.related:  # type: ignore[attr-defined]
        for c in rel.candidates:
            for api, evidence in c.sources.items():
                for e in evidence:
                    doc = stack.documents.get_document(BuildId(builds[api].value), e.doc_id)
                    assert doc is not None, e
                    assert quote_in(e.quote, _doc_text(doc)), (api, e)


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("shopify-mini", "woo-mini"):
        s.load(str(packages / p))
    return s


def test_id_fields_count_only_when_their_description_names_the_target(stack: FakeStack) -> None:
    r = stack.suggest_related().execute(["shopify", "woocommerce"], "Product")
    by_child = {c.child: c for rel in r.related for c in rel.candidates if c.parent == "product"}
    variant = by_child["variant"]
    (ev,) = variant.sources["shopify"]
    assert (ev.kind, ev.paths) == ("id_field", ("products[].variants[].product_id",))
    assert "parent product" in ev.quote
    assert [(o.kind, o.cardinality) for o in variant.options(r.labels)] == [("reference", "n:1")]
    assert "lineitem" in by_child
    _assert_cited(stack, r)


def test_unknown_concept_and_paging(stack: FakeStack) -> None:
    r = stack.suggest_related().execute(["shopify", "woocommerce"], "Nothing Here")
    assert (r.total, r.related, r.aliases) == (0, (), ())
    full = stack.suggest_related().execute(["shopify", "woocommerce"], "Product")
    page = stack.suggest_related().execute(["shopify", "woocommerce"], "Product", 1, 1)
    assert page.related == full.related[1:2]


# -- the real 1.2 renders (opt-in, like the suggest-v2 tests) -----------------------------------

PATHS = [str(p) for p in real_packages("suggest")]
real = pytest.mark.skipif(
    len(PATHS) != 3, reason="the pinned suggest packages (tests/real_packages.toml) are not there"
)
APIS = ["shopify", "woocommerce", "mirakl"]


@pytest.fixture(scope="module")
def real_stack() -> FakeStack:
    s = FakeStack()
    for path in PATHS:
        s.load(path)
    return s


@real
def test_real_product_variant_and_the_variation_alias(real_stack: FakeStack) -> None:
    r = real_stack.suggest_related().execute(APIS, "Product", limit=100)
    kinds = {rel.key: rel.kinds for rel in r.related}
    assert {"nested", "sub_resource", "id_field"} <= set(kinds["variant"]["shopify"])
    assert "sub_resource" in kinds["variation"]["woocommerce"]
    assert {"admin", "boolean", "create", "cancel"}.isdisjoint(kinds)
    variant = next(c for rel in r.related for c in rel.candidates if c.id == "product>variant")
    assert [o.kind for o in variant.options(r.labels)] == ["embedded", "reference"]
    (alias,) = [a for a in r.aliases if set(a.names.values()) == {"variant", "variation"}]
    assert alias.names == {"shopify": "variant", "woocommerce": "variation"}
    assert (
        alias.evidence["shopify"].fetch
        == "GET /admin/api/{version}/products/{product_id}/variants.json"
    )
    assert (
        alias.evidence["woocommerce"].fetch
        == "GET /wp-json/wc/{version}/products/{product_id}/variations"
    )
    _assert_cited(real_stack, r)


@real
def test_real_refund_parent_id_names_the_order(real_stack: FakeStack) -> None:
    r = real_stack.suggest_related().execute(APIS, "Order", limit=100)
    refund = next(c for rel in r.related for c in rel.candidates if c.id == "order>refund")
    woo = [e for e in refund.sources["woocommerce"] if e.kind == "id_field"]
    assert any(e.paths[0].endswith("parent_id") and "order" in e.quote.lower() for e in woo)
    assert all(api in refund.sources for api in APIS)
    _assert_cited(real_stack, r)


@real
def test_real_alias_brings_woocommerce_variations_to_the_variant_member(
    real_stack: FakeStack,
) -> None:
    sets = real_stack.model_sets()

    def woo_docs(aliases: list[dict[str, object]]) -> list[str]:
        s = sets.start(["shopify", "woocommerce"], ["Product", "Variant"], aliases=aliases)
        ctx = sets.context(s.session_id)
        variant = next(m for m in ctx["members"] if m["concept"] == "Variant")
        woo = next(a for a in variant["apis"] if a["api"] == "woocommerce")
        return [d["endpoint"] or d["doc_id"] for d in woo["documents"]]

    without = woo_docs([])
    with_alias = woo_docs([{"concept": "Variant", "names": {"woocommerce": "variation"}}])
    assert not any("variations" in d for d in without)
    assert any("/variations" in d for d in with_alias)


@real
def test_real_find_fact_owner_as_method_and_path(real_stack: FakeStack) -> None:
    """The tester's call: owner "GET /api/products" (as endpoints are shown) on Mirakl."""
    cases = [
        ("mirakl", "shop_id", "GET /api/products"),
        ("shopify", "limit", "GET /admin/api/2026-10/products.json"),
        ("woocommerce", "per_page", "GET /wp-json/wc/v3/products"),
    ]
    for api, name, owner in cases:
        r = real_stack.find_fact().execute(api, name, kind="field", location="query", owner=owner)
        assert r.found, (api, owner)
        assert all(m.owner_id.startswith("endpoint:GET~") for m in r.matches), api
    # the tester's exact call: no longer "not in build"; offset just isn't documented there
    r = real_stack.find_fact().execute(
        "mirakl", "offset", kind="field", location="query", owner="GET /api/products"
    )
    assert not r.found


@real
def test_real_models_follow_item_model_refs(real_stack: FakeStack) -> None:
    """WooCommerce Order.line_items -> orderlineitem; Shopify Product.variants -> productvariant."""
    from plume.domain.shared.ids import BuildId  # noqa: PLC0415

    for api, doc_id, path, source in (
        ("woocommerce", "model:order", "line_items[].sku", "orderlineitem.schema.json#"),
        ("shopify", "model:product", "variants[].sku", "productvariant.schema.json#"),
    ):
        build = BuildId(real_stack.resolver().resolve(api).build.build_id.value)
        doc = real_stack.documents.get_document(build, doc_id)
        assert doc is not None
        spec = next((f for f in doc.fields if f.name == path), None)
        assert spec is not None, (api, path)
        assert spec.description
        assert (spec.pointer or "").startswith(source)
        assert real_stack.fact_query.find(build, path), (api, path)  # it is a fact too


@real
def test_real_suggestions_merge_item_models_and_skip_link_noise(real_stack: FakeStack) -> None:
    """Round 2: Image has WooCommerce evidence (product.images[] items are productimage),
    line items and collects are one concept each, and link/id-list/sub-collection keys are
    no concepts."""
    r = real_stack.suggest_related().execute(APIS[:2], "Product", limit=100)
    kinds = {rel.key: rel.kinds for rel in r.related}
    assert kinds["image"]["woocommerce"]
    assert kinds["lineitem"]["woocommerce"]
    for gone in ("productimage", "orderlineitem", "customcollectioncollect", "previous",
                 "productid", "customer", "report"):  # fmt: skip
        assert gone not in kinds, gone


@real
def test_real_set_candidates_merge_an_accepted_alias(real_stack: FakeStack) -> None:
    sets = real_stack.model_sets()
    alias = [{"concept": "Variant", "names": {"woocommerce": "variation"}}]
    session = sets.start(APIS[:2], ["Product", "Variant"], aliases=alias)
    cands = {c["id"]: c for c in sets.context(session.session_id)["relation_candidates"]}
    assert cands["product>variant"]["sources"]["woocommerce"]  # not only on the alias entry


@real
def test_real_bundled_response_models_name_their_operation(real_stack: FakeStack) -> None:
    models = real_stack.models()
    session = models.start(["mirakl", "shopify"], "Product")  # the tester's session
    docs = {d["doc_id"]: d for a in models.context(session.session_id)["apis"]
            for d in a["documents"]}  # fmt: skip
    assert docs["model:p11-response-200-products"]["endpoint"] == "GET /api/products/offers"


@real
def test_real_relation_sources_prefer_where_the_api_is_read(real_stack: FakeStack) -> None:
    """Round 3: WooCommerce Product > Image cites model:product images[] and GET responses, not
    only the create[]/update[] paths of POST /products/batch."""
    r = real_stack.suggest_related().execute(APIS[:2], "Product", limit=100)
    image = next(x for x in r.related if x.key == "image")
    woo = next(c for c in image.candidates if c.id == "product>image").sources["woocommerce"]
    assert woo
    assert all(e.read for e in woo)
    assert woo[0].doc_id == "model:product"
    assert not any("batch" in e.doc_id for e in woo)


@real
def test_real_image_member_context_lists_the_parent_scoped_documents(
    real_stack: FakeStack,
) -> None:
    models = real_stack.models()
    session = models.start(APIS[:2], "Image")
    docs = {a["api"]: [d["doc_id"] for d in a["documents"]]
            for a in models.context(session.session_id)["apis"]}  # fmt: skip
    assert any("/products/{product_id}/images" in d for d in docs["shopify"])
    assert docs["woocommerce"][0] == "model:productimage"
