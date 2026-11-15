import json
from pathlib import Path
from typing import Any

import pytest

from plume.application.errors import NotFoundError
from plume.application.models.concepts import ModelInputError, concept_key
from plume.application.models.sessions import ModelDraftRefusedError
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]


def _draft(name: str) -> dict[str, Any]:
    return json.loads((DRAFTS / f"catalog-order-{name}.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog", "shopify-mini"):
        s.load(str(packages / p))
    return s


def test_concept_keys() -> None:
    assert concept_key("Orders") == concept_key("order") == "order"
    assert concept_key("Categories") == "category"
    assert concept_key("DraftOrder") == "draftorder"
    assert concept_key("address") == "address"


def test_suggest_concepts(stack: FakeStack) -> None:
    s = stack.suggest().execute(APIS)
    keys = [c.key for c in s.concepts]
    assert keys[:2] == ["order", "product"] or keys[:2] == ["product", "order"]
    order = next(c for c in s.concepts if c.key == "order")
    assert order.coverage == {"test-catalog-api": "direct", "second-catalog-api": "direct"}
    assert order.difficulty == ("ok", "Straightforward")
    assert order.likely_fields >= 6
    assert "read" in order.operations
    assert "model:order" in order.doc_ids["test-catalog-api"]
    assert "error" not in keys  # noise


def test_suggest_with_partial_coverage(stack: FakeStack) -> None:
    s = stack.suggest().execute(["shopify", "test-catalog-api"])
    product = next(c for c in s.concepts if c.key == "product")
    assert product.coverage["shopify"] == "direct"
    assert s.not_modeled > 0


def test_suggest_validation(stack: FakeStack) -> None:
    with pytest.raises(ModelInputError):
        stack.suggest().execute(["shopify"])
    with pytest.raises(ModelInputError):
        stack.suggest().execute(["shopify", "shopify"])
    with pytest.raises(NotFoundError):
        stack.suggest().execute(["shopify", "nope"])


def test_session_and_context(stack: FakeStack) -> None:
    session = stack.models().start(APIS, "Order")
    assert [i.api for i in session.inputs] == APIS
    ctx = stack.models().context(session.session_id)
    assert ctx["concept"] == "Order"
    apis = {a["api"]: a for a in ctx["apis"]}
    docs = apis["test-catalog-api"]["documents"]
    assert docs[0]["doc_id"] == "model:order"  # models first
    paths = {f["path"] for d in docs for f in d["fields"]}
    assert {"total", "orders[].total"} <= paths
    assert "submit_model_draft" in ctx["instructions"]
    assert ctx["draft_format"]["fields"][0]["sources"]
    with pytest.raises(NotFoundError):
        stack.models().context("s-nope")


def test_good_draft_becomes_an_immutable_snapshot(stack: FakeStack) -> None:
    models = stack.models()
    session = models.start(APIS, "Order")
    result = models.submit(session.session_id, _draft("good"))
    assert result.created
    snap = result.snapshot
    assert snap.status == "generated_unverified"
    assert snap.citations_checked == 10
    assert snap.coverage() == {"test-catalog-api": (5, 5), "second-catalog-api": (5, 5)}
    again = models.submit(session.session_id, _draft("good"))
    assert not again.created
    assert again.snapshot.snapshot_id == snap.snapshot_id
    assert models.snapshot(snap.snapshot_id) == snap
    assert models.existing(APIS, "orders") == snap
    assert [m.snapshot_id for m in models.list("second-catalog-api")] == [snap.snapshot_id]
    assert models.list("shopify") == []


@pytest.mark.parametrize(
    "name",
    [
        "missing-citation",
        "quote-not-in-doc",
        "field-not-in-api",
        "api-not-in-session",
        "endpoint-not-in-api",
        "doc-not-in-build",
    ],
)
def test_bad_drafts_are_refused_with_a_precise_code(stack: FakeStack, name: str) -> None:
    raw = _draft(f"bad-{name}")
    session = stack.models().start(APIS, "Order")
    with pytest.raises(ModelDraftRefusedError) as info:
        stack.models().submit(session.session_id, raw)
    assert [i.code for i in info.value.issues] == [raw["_expect_code"]]
    assert stack.models_repo.snapshots == {}


def test_format_error_is_a_refusal(stack: FakeStack) -> None:
    session = stack.models().start(APIS, "Order")
    with pytest.raises(ModelDraftRefusedError) as info:
        stack.models().submit(session.session_id, {"name": "x", "fields": []})
    assert info.value.issues[0].code == "INVALID_FORMAT"


def test_bundled_models_suggest_by_leaf_name(packages: Path) -> None:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "mirakl-mini"))
    s.load(str(packages / "shopify-mini"))
    keys = {c.key: c for c in s.suggest().execute(["mirakl", "shopify"]).concepts}
    assert keys["address"].coverage == {"mirakl": "direct", "shopify": "direct"}
    assert keys["customer"].coverage["mirakl"] == "direct"
    assert not any("response" in k for k in keys)  # bundle roots are not concepts
    counts = s.overviews().one("mirakl").counts
    assert (counts["model"], counts["model_shapes"]) == (12, 11)
    # billing info, boolean, date, link, address, customer, orders (the 2 roots are no names)
    assert counts["model_names"] == 7
