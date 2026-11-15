import pytest

from plume.domain.eval.gate import GatePolicy, decide
from plume.domain.eval.gold import GoldKind, GoldQuestion, GoldSet
from plume.domain.eval.metrics import QuestionOutcome, score

Q = [
    GoldQuestion("a", GoldKind.SEARCH, "q a", ("d1",)),
    GoldQuestion("b", GoldKind.SEARCH, "q b", ("d2", "d3")),
    GoldQuestion("c", GoldKind.ABSENT, "nope", fact_name="nope"),
    GoldQuestion("d", GoldKind.PRESENT, "sku", fact_name="sku"),
]


def test_score() -> None:
    m = score(
        Q,
        [
            QuestionOutcome("a", GoldKind.SEARCH, ranked=("d1", "x")),
            QuestionOutcome("b", GoldKind.SEARCH, ranked=("x", "y", "d3")),
            QuestionOutcome("c", GoldKind.ABSENT, found=False, complete=True),
            QuestionOutcome("d", GoldKind.PRESENT, found=True),
        ],
    )
    assert m.recall_at_k == 1.0
    assert m.mrr == pytest.approx((1 + 1 / 3) / 2, abs=1e-4)
    assert m.citation_hit_rate == 0.5
    assert m.fact_accuracy == 1.0
    assert (m.questions, m.search_questions, m.fact_questions) == (4, 2, 2)


def test_absent_needs_complete_and_rank_beyond_k() -> None:
    m = score(
        Q,
        [
            QuestionOutcome("a", GoldKind.SEARCH, ranked=("1", "2", "3", "4", "5", "d1")),
            QuestionOutcome("b", GoldKind.SEARCH, ranked=(), missing_expected=("d2",)),
            QuestionOutcome("c", GoldKind.ABSENT, found=False, complete=False),
            QuestionOutcome("d", GoldKind.PRESENT, found=False),
        ],
    )
    assert m.recall_at_k == 0.0
    assert m.fact_accuracy == 0.0
    assert m.missing_expected == 1
    with pytest.raises(ValueError, match="one outcome"):
        score(Q, [])
    assert m.as_dict()["k"] == 5
    assert type(m).from_dict(m.as_dict()) == m


def test_gate_floor_and_drop() -> None:
    good = score(Q[:1], [QuestionOutcome("a", GoldKind.SEARCH, ranked=("d1",))])
    bad = score(Q[:1], [QuestionOutcome("a", GoldKind.SEARCH, ranked=("x", "d1"))])
    assert decide(GatePolicy(), good).passed
    d = decide(GatePolicy(), bad, live=good)
    assert not d.passed
    assert "MRR fell from 1.00 to 0.50" in d.message
    assert decide(GatePolicy(max_drop=0.6), bad, live=good).passed
    floor = decide(
        GatePolicy(min_recall=0.9), score(Q[:1], [QuestionOutcome("a", GoldKind.SEARCH)])
    )
    assert "below the floor" in floor.message
    assert decide(GatePolicy(), good).message == "Quality gate passed."


def test_gold_validation() -> None:
    with pytest.raises(ValueError, match="expected documents"):
        GoldQuestion("x", GoldKind.SEARCH, "q")
    with pytest.raises(ValueError, match="fact_name"):
        GoldQuestion("x", GoldKind.ABSENT, "q")
    with pytest.raises(ValueError, match="duplicate"):
        GoldSet("api", (Q[0], Q[0]))
    with pytest.raises(ValueError, match="at least one"):
        GoldSet("api", ())
