"""ModelEvaluation over stored models: gold files from the configured dirs or one file, held-out
results apart, and the release gate (invented = 0; recall once a threshold is set)."""

import json
from pathlib import Path
from typing import Any

import pytest

from plume.application.errors import NotFoundError
from plume.application.models.model_eval import ModelEvaluation
from plume.application.models.sessions import ModelSessions, ModelStateError
from plume.domain.models.model_eval import ModelGatePolicy
from plume.infrastructure.models.gold_files import JsonModelGold
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
A, B = APIS


def _gold(held_out: bool = False, **total: Any) -> dict[str, Any]:
    return {
        "schema": "plume.model-gold.v1",
        "concept": "Order",
        "apis": APIS,
        "heldOut": held_out,
        "fields": [
            {"name": "id", "apis": {A: {"paths": ["id"]}, B: {"paths": ["id"]}}},
            {"name": "grand_total", "aliases": ["total"], "apis": {
                A: {"paths": ["orders[].total"], "conversion": {"kind": "money-decimal-string"}},
                B: {"paths": total.get("b", ["total"])}}},
            {"name": "status", "apis": {A: {"notAvailable": True}, B: {"notAvailable": True}}},
        ],
    }  # fmt: skip


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


def _setup(
    stack: FakeStack, tmp_path: Path, golds: dict[str, dict[str, Any]], min_recall: float | None
) -> tuple[ModelSessions, ModelEvaluation, str]:
    folder = tmp_path / "gold"
    folder.mkdir()
    for name, gold in golds.items():
        (folder / name).write_text(json.dumps(gold))
    plain = stack.models()
    evaluation = ModelEvaluation(
        stack.models_repo, stack.sets_repo, plain.oracle_for, JsonModelGold((folder,)),
        ModelGatePolicy(min_recall),
    )  # fmt: skip
    gated = ModelSessions(
        stack.resolver(), stack.search_index, stack.fact_query, stack.documents,
        stack.models_repo, stack.clock, release_gate=evaluation.gate,
    )  # fmt: skip
    session = gated.start(APIS, "Order")
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    snap = gated.submit(session.session_id, draft, maintainer=True).snapshot
    return gated, evaluation, snap.snapshot_id


def test_evaluate_with_all_gold_and_held_out_apart(stack: FakeStack, tmp_path: Path) -> None:
    golds = {"order-1.json": _gold(), "order-1-held.json": _gold(held_out=True)}
    _, evaluation, sid = _setup(stack, tmp_path, golds, None)
    report: dict[str, Any] = evaluation.evaluate(sid).as_dict()
    assert [r["gold"] for r in report["results"]] == ["order-1-held.json", "order-1.json"]
    tuning, held = report["tuning"], report["heldOut"]
    assert tuning["models"] == held["models"] == 1
    assert tuning["recall"] == 1.0
    result = report["results"][1]
    assert result["counts"] == {"correct": 4, "not_available_correct": 2}
    assert result["conversionMissingRate"] == 0.0  # it says "parse decimal string"
    one = evaluation.evaluate(sid, str(tmp_path / "gold" / "order-1.json"))
    assert [r.gold for _, r in one.results] == ["order-1.json"]


def test_no_covering_gold(stack: FakeStack, tmp_path: Path) -> None:
    other = {**_gold(), "concept": "Customer"}
    _, evaluation, sid = _setup(stack, tmp_path, {"customer.json": other}, None)
    assert evaluation.evaluate(sid).results == ()
    with pytest.raises(NotFoundError, match="has no gold for"):
        evaluation.evaluate(sid, str(tmp_path / "gold" / "customer.json"))
    with pytest.raises(NotFoundError, match="no model or model set"):
        evaluation.evaluate("m-nope")


def test_release_gate_recall(stack: FakeStack, tmp_path: Path) -> None:
    wrong = _gold(b=["currency"])  # gold: B's total is "currency"; the model maps "total"
    models, evaluation, sid = _setup(stack, tmp_path, {"order.json": wrong}, 0.9)
    assert evaluation.evaluate(sid).results[0][1].recall == 0.75
    with pytest.raises(
        ModelStateError, match=r"fails the model gold gate: order\.json: recall 0\.75"
    ):
        models.release(sid)


def test_release_passes_without_threshold_or_gold(stack: FakeStack, tmp_path: Path) -> None:
    models, _, sid = _setup(stack, tmp_path, {"order.json": _gold(b=["currency"])}, None)
    assert models.release(sid).visibility == "official"  # invented = 0; no threshold yet


def test_invented_blocks_release(stack: FakeStack, tmp_path: Path) -> None:
    models, evaluation, sid = _setup(stack, tmp_path, {"order.json": _gold()}, None)
    # the pinned build loses a field the model maps (a reload): the mapping is now invented
    original = evaluation._oracle_for

    def without_number(inputs):  # type: ignore[no-untyped-def]
        oracle = original(inputs)
        exists = oracle.field_exists
        return type(oracle)(oracle.doc_text, lambda a, p: p != "id" and exists(a, p),
                            oracle.endpoint_exists, oracle.write_only)  # fmt: skip

    evaluation._oracle_for = without_number
    with pytest.raises(ModelStateError, match="2 invented mapping"):
        models.release(sid)


def test_a_reason_releases_over_low_recall(stack: FakeStack, tmp_path: Path) -> None:
    models, _, sid = _setup(stack, tmp_path, {"order.json": _gold(b=["currency"])}, 0.9)
    with pytest.raises(ModelStateError, match="may release over it with a reason"):
        models.release(sid)
    with pytest.raises(ModelStateError):
        models.release(sid, override_reason="   ")  # blank is no reason
    released = models.release(sid, override_reason="Mirakl gold pending review")
    assert released.visibility == "official"
    override = released.release_override
    assert override is not None
    assert override["reason"] == "Mirakl gold pending review"
    assert override["failures"] == ["order.json: recall 0.75 below 0.9"]
    assert override["at"]


def test_no_reason_overrides_an_invented_mapping(stack: FakeStack, tmp_path: Path) -> None:
    models, evaluation, sid = _setup(stack, tmp_path, {"order.json": _gold()}, None)
    original = evaluation._oracle_for

    def without_id(inputs):  # type: ignore[no-untyped-def]
        oracle = original(inputs)
        exists = oracle.field_exists
        return type(oracle)(oracle.doc_text, lambda a, p: p != "id" and exists(a, p),
                            oracle.endpoint_exists, oracle.write_only)  # fmt: skip

    evaluation._oracle_for = without_id
    with pytest.raises(ModelStateError, match="invented mapping"):
        models.release(sid, override_reason="ship it")
    assert models.snapshot(sid).visibility == "unreleased"
