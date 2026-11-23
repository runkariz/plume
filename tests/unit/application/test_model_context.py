"""Model context: concept names as people type them, the concept's own read documents first,
no error models, and a note when an API has no resource of the concept's own."""

from pathlib import Path
from typing import Any

import pytest

from plume.application.models import sessions
from plume.application.models.concepts import concept_parts
from plume.application.models.sessions import _error_model
from plume.application.ports.search_index import DocumentSummary
from plume.domain.knowledge.document import DocumentKind
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("Order", (("order",), ())),
        ("Order (with order line)", (("order",), ("orderline",))),
        ("Order (+ order line)", (("order",), ("orderline",))),
        ("Product / Offer (+ variant / SKU)", (("product", "offer"), ("variant", "sku"))),
        ("Inventory / Stock", (("inventory", "stock"), ())),
        ("line_items", (("lineitem",), ())),
    ],
)
def test_concept_parts(name: str, parts: tuple[tuple[str, ...], tuple[str, ...]]) -> None:
    assert concept_parts(name) == parts


def _model(doc_id: str, title: str = "x") -> DocumentSummary:
    return DocumentSummary(doc_id, DocumentKind.MODEL, title, None, None, None, False)


@pytest.mark.parametrize(
    ("doc_id", "error"),
    [
        ("model:or07-response-200-orderlines-errors", True),
        ("model:problemdetail", True),
        ("model:shipment-400", True),
        ("model:producterror", True),
        ("model:or11-response-200-orders", False),
        ("model:order", False),
    ],
)
def test_error_models(doc_id: str, error: bool) -> None:
    assert _error_model(_model(doc_id)) is error


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog", "shopify-mini"):
        s.load(str(packages / p))
    return s


def _docs(stack: FakeStack, concept: str, apis: list[str]) -> dict[str, dict[str, Any]]:
    models = stack.models()
    ctx = models.context(models.start(apis, concept).session_id)
    return {e["api"]: e for e in ctx["apis"]}


def test_a_decorated_name_finds_the_concept(stack: FakeStack) -> None:
    apis = ["test-catalog-api", "second-catalog-api"]
    plain = _docs(stack, "Order", apis)
    decorated = _docs(stack, "Order (with order line)", apis)
    for api in apis:
        ids = [d["doc_id"] for d in decorated[api]["documents"]]
        assert ids[:2] == [d["doc_id"] for d in plain[api]["documents"]][:2]
        assert "model:order" in ids
        assert "note" not in decorated[api]


def test_no_resource_of_its_own_is_said(stack: FakeStack) -> None:
    ctx = _docs(stack, "Order", ["test-catalog-api", "shopify"])
    assert "note" not in ctx["test-catalog-api"]
    assert str(ctx["shopify"]["note"]).startswith("shopify has no Order resource of its own")


def test_children_without_the_concept_itself_do_not_loop(stack: FakeStack) -> None:
    """Only child keys match ("line" -> lineitem) and no endpoint names the concept: the
    fallback runs once (a RecursionError on plume-l2 for Customer on ebay-sell + bol-retailer)."""
    for concept in ("Line", "Line (with item)", "Line / Row"):
        ctx = _docs(stack, concept, ["test-catalog-api", "shopify"])
        assert "note" in ctx["shopify"]
        assert len(ctx["shopify"]["documents"]) <= 30


@pytest.mark.anyio
async def test_mcp_tool_bugs_carry_a_short_message() -> None:
    from mcp.server.mcpserver.exceptions import ToolError  # noqa: PLC0415

    from plume.interfaces.mcp.reader_server import _run  # noqa: PLC0415

    def broken() -> dict[str, object]:
        raise RecursionError("maximum recursion depth exceeded in /secret/path")

    with pytest.raises(
        ToolError, match=r"internal error \(RecursionError\); .* as ref [0-9a-f]{8}"
    ) as err:
        await _run(broken)
    assert "/secret/path" not in str(err.value)


def test_kinds_of_the_concept_by_role_name_are_in_its_context(
    packages: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """set-g1 (4): Mirakl's order customer billing address (model "Customer / Billing Address",
    key billingaddress) was missing from an Address context."""
    monkeypatch.setattr(sessions, "MIN_OWN_DOCS", 0)  # no text fill: the ranking alone
    s = FakeStack(embedder=WordEmbedder())
    for p in ("mirakl-mini", "shopify-mini"):
        s.load(str(packages / p))
    models = s.models()
    ctx = models.context(models.start(["mirakl", "shopify"], "Address").session_id)
    ids = [d["doc_id"] for e in ctx["apis"] if e["api"] == "mirakl" for d in e["documents"]]
    assert "model:or11-response-200-orders-customer-billingaddress" in ids
    assert "model:dr12-response-200-data-shippingto-address" in ids


def test_size_does_not_beat_relevance() -> None:
    """order-g4 / customer-g4: Shopware's 1,900-field ordertag and orderdeliveryposition ranked
    above orderlineitem / orderaddress; role parts now lead within a tier."""
    from plume.application.models.sessions import _role_part  # noqa: PLC0415

    assert _role_part("orderlineitem", ("order",))
    assert _role_part("orderaddress", ("order",))
    assert _role_part("customeraddress", ("customer",))
    assert not _role_part("ordertag", ("order",))
    assert not _role_part("orderdeliveryposition", ("order",))


def test_a_sub_resource_of_another_resource_is_not_the_concepts_own_read() -> None:
    """BigCommerce /orders/{order_id}/products is order lines, not Product's own read."""
    from plume.application.models.sessions import _under_other_resource  # noqa: PLC0415

    assert _under_other_resource("/{version}/orders/{order_id}/products", ("product",))
    assert not _under_other_resource("/{version}/catalog/products", ("product",))
    assert not _under_other_resource("/{version}/catalog/products/{product_id}", ("product",))
    assert not _under_other_resource("/api/{version}/orders/{id}", ("order",))
    assert not _under_other_resource("/admin/api/{version}/orders/{order_id}.json", ("order",))


def test_an_api_without_the_concept_gets_the_models_that_embed_it() -> None:
    """eBay Sell has no customer resource: its customer is the order's buyer and shipTo; the
    context held policies and metrics. Reads embedding it (more role fields first) lead."""
    from types import SimpleNamespace  # noqa: PLC0415

    from plume.domain.knowledge.fact import FactKind  # noqa: PLC0415

    def field(owner: str, name: str, type_: str | None = "object") -> Any:
        return SimpleNamespace(owner_id=owner, name=name, type=type_, kind=FactKind.FIELD)

    order, orders = "endpoint:GET~/order/{id}", "endpoint:GET~/order"
    quote = "endpoint:POST~/shipping_quote"
    found = {
        "buyer": [field(order, "buyer"), field(orders, "orders[].buyer"), field(quote, "buyer")],
        "shipto": [field(order, "fulfillment[].shippingStep.shipTo"), field(quote, "shipTo")],
        "customer": [field("model:x", "customer", "string")],  # a scalar: not the concept
    }
    stub = SimpleNamespace(
        _facts=SimpleNamespace(find=lambda b, n, kind=None: found.get(n.lower(), [])),
        _index=SimpleNamespace(summaries=lambda b, ids: {i: _model(i) for i in ids}),
    )
    docs = sessions.ModelSessions._embedding_docs(stub, "Customer", None)  # type: ignore[arg-type]
    assert [d.doc_id for d in docs] == [order, orders, quote]  # reads first, then the write


def test_kinds_count_as_the_concept_when_it_has_no_documents_of_its_own() -> None:
    """Google Merchant Inventory: localinventory / regionalinventory were left out (only names
    starting with "inventory" counted)."""
    from plume.application.models.sessions import _kinds  # noqa: PLC0415

    groups = {k: [_model(f"model:{k}")] for k in (
        "localinventory", "regionalinventory", "lfpinventory", "instock",
        "inventoryloyaltyprogram", "listlocalinventoriesresponse")}  # fmt: skip
    assert _kinds(("inventory", "stock"), groups) == [
        "lfpinventory",
        "localinventory",
        "regionalinventory",
    ]  # "in" is no qualifier; a response wrapper is no kind
    assert _kinds(("inventory",), {**groups, "inventory": [_model("model:inventory")]}) == []


def test_a_concept_synonym_counts_only_when_the_api_lacks_the_concept_name() -> None:
    """JTL-Wawi calls products "items" (a noise word elsewhere, so it has no group): Product's
    context missed GET /items. Where products exist, items stay out."""
    from plume.application.models.sessions import _synonyms  # noqa: PLC0415

    items = DocumentSummary("endpoint:GET~/items", DocumentKind.ENDPOINT, "Items", "Item",
                            "GET", "/{version}/items", False)  # fmt: skip
    groups: dict[str, list[DocumentSummary]] = {"offer": [_model("model:offer")]}
    assert _synonyms(("product", "offer"), groups, [items]) == ["item"]
    assert groups["item"] == [items]  # its group built on the spot
    with_products = {"product": [_model("model:product")]}
    assert _synonyms(("product",), with_products, [items]) == []


def test_a_path_starting_with_the_concepts_id_is_under_it() -> None:
    """meta-commerce-platform: GET /{order_id}/items, /{ORDER_ID}/payments and /{order_id}/
    shipments (the package labels them Payment / Api) belong in an Order context."""
    from plume.application.models.sessions import _under  # noqa: PLC0415

    order = ("order",)
    for path in ("/{order_id}/items", "/{ORDER_ID}/payments", "/{orderId}/shipments",
                 "/{version}/{order_id}/items", "/orders/{id}"):  # fmt: skip
        assert _under(path, order), path
    others = ("/{PAGE_ID}/commerce_orders", "/{order_line_id}/x", "/{cms_id}/apps",
              "/shipment-management/delivery-proposals/{orderId}")  # fmt: skip
    for path in others:
        assert not _under(path, order), path  # another resource's id, or deeper in its path
