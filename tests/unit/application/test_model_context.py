"""Model context: concept names as people type them, the concept's own read documents first,
no error models, and a note when an API has no resource of the concept's own."""

from pathlib import Path
from typing import Any

import pytest

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
