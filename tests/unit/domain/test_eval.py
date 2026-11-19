import pytest

from plume.domain.eval.gate import GatePolicy, decide
from plume.domain.eval.gold import GoldKind, GoldQuestion, GoldSet
from plume.domain.eval.metrics import (
    EvalMetrics,
    QuestionOutcome,
    SourceMetrics,
    few_questions_note,
    score,
)

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
    assert m.top1_rate == 0.5
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


MIXED = [
    GoldQuestion("d1", GoldKind.SEARCH, "docs 1", ("a",)),
    GoldQuestion("d2", GoldKind.SEARCH, "docs 2", ("b",), source="docs"),
    GoldQuestion("s1", GoldKind.SEARCH, "spec 1", ("c",), source="spec"),
    GoldQuestion("s2", GoldKind.SEARCH, "spec 2", ("model:x",), source="spec"),
]


def _mixed(spec_ranks: tuple[tuple[str, ...], tuple[str, ...]]) -> EvalMetrics:
    return score(
        MIXED,
        [
            QuestionOutcome("d1", GoldKind.SEARCH, ranked=("a",)),
            QuestionOutcome("d2", GoldKind.SEARCH, ranked=("x", "b")),
            QuestionOutcome("s1", GoldKind.SEARCH, ranked=spec_ranks[0]),
            QuestionOutcome("s2", GoldKind.SEARCH, ranked=spec_ranks[1]),
        ],
    )


def test_metrics_per_source_and_combined() -> None:
    m = _mixed((("c",), ("y",)))
    docs, spec = m.source("docs"), m.source("spec")
    assert docs == SourceMetrics(1.0, 0.75, 0.5, 2)
    assert spec == SourceMetrics(0.5, 0.5, 0.5, 2)
    assert (m.recall_at_k, m.mrr, m.top1_rate) == (0.75, 0.625, 0.5)
    assert m.source("combined") == m.combined
    assert EvalMetrics.from_dict(m.as_dict()) == m
    assert set(m.as_dict()["by_source"]) == {"docs", "spec"}


def test_records_without_sources_read_as_docs() -> None:
    old = score(
        Q,
        [
            QuestionOutcome("a", GoldKind.SEARCH, ranked=("d1",)),
            QuestionOutcome("b", GoldKind.SEARCH),
            QuestionOutcome("c", GoldKind.ABSENT, found=False, complete=True),
            QuestionOutcome("d", GoldKind.PRESENT, found=True),
        ],
    )
    stored = {k: v for k, v in old.as_dict().items() if k != "by_source"}  # before sources
    m = EvalMetrics.from_dict(stored)
    assert m.by_source == ()
    assert m.source("docs") == m.combined
    assert m.source("spec") is None


def test_gate_reads_the_chosen_source_and_checks_each_for_regression() -> None:
    m = _mixed((("c",), ("y",)))  # docs recall 1.0, spec 0.5, combined 0.75
    assert decide(GatePolicy(min_recall=0.7), m).passed
    assert decide(GatePolicy(min_recall=0.7, source="docs"), m).passed
    spec = decide(GatePolicy(min_recall=0.7, source="spec"), m)
    assert "recall@5 (spec questions) 0.50 is below the floor 0.70" in spec.message
    docs_only = score(Q[:1], [QuestionOutcome("a", GoldKind.SEARCH, ranked=("d1",))])
    assert decide(GatePolicy(source="spec"), docs_only).passed  # no spec questions: combined
    # Spec falls by 0.5 while combined falls by 0.25: both are reported, docs is not.
    worse = _mixed((("y",), ("y",)))
    d = decide(GatePolicy(min_recall=0.0), worse, live=m)
    assert "recall@5 fell from 0.75 to 0.50" in d.message
    assert "recall@5 (spec questions) fell from 0.50 to 0.00" in d.message
    assert "docs questions" not in d.message
    with pytest.raises(ValueError, match="gate source"):
        GatePolicy(source="both")


def test_gold_source_must_be_a_lowercase_label() -> None:
    assert GoldQuestion("x", GoldKind.SEARCH, "q", ("d",), source="sdk").source == "sdk"
    for bad in ("SDK", "", "two words", "-x"):
        with pytest.raises(ValueError, match="must be a lowercase label"):
            GoldQuestion("x", GoldKind.SEARCH, "q", ("d",), source=bad)


def test_top1_rate_reads_the_old_stored_name() -> None:
    old = {
        "recall_at_k": 0.9,
        "mrr": 0.8,
        "citation_hit_rate": 0.7,  # eval results stored before the rename
        "fact_accuracy": 1.0,
        "missing_expected": 0,
        "questions": 12,
        "search_questions": 10,
        "fact_questions": 2,
        "by_source": {
            "docs": {
                "recall_at_k": 0.9,
                "mrr": 0.8,
                "citation_hit_rate": 0.6,
                "search_questions": 10,
            }
        },
    }
    m = EvalMetrics.from_dict(old)
    assert m.top1_rate == 0.7
    assert dict(m.by_source)["docs"].top1_rate == 0.6
    out = m.as_dict()
    assert out["top1_rate"] == 0.7
    assert "citation_hit_rate" not in out
    assert out["by_source"]["docs"]["top1_rate"] == 0.6
    assert EvalMetrics.from_dict(out) == m


def test_few_questions_note() -> None:
    assert few_questions_note(9) == "Too few questions to measure; a sanity check only."
    assert few_questions_note(10) is None


def test_any_lowercase_source_label_is_reported_apart() -> None:
    from plume.domain.eval.gold import source_order  # noqa: PLC0415

    qs = [
        GoldQuestion("t1", GoldKind.SEARCH, "q", ("d1",), source="tester"),
        GoldQuestion("r1", GoldKind.SEARCH, "q", ("d2",), source="real-queries"),
        GoldQuestion("d1", GoldKind.SEARCH, "q", ("d1",)),
    ]
    m = score(
        qs,
        [
            QuestionOutcome("t1", GoldKind.SEARCH, ranked=("d1",)),
            QuestionOutcome("r1", GoldKind.SEARCH, ranked=("x",)),
            QuestionOutcome("d1", GoldKind.SEARCH, ranked=("d1",)),
        ],
    )
    assert [name for name, _ in m.by_source] == ["docs", "tester", "real-queries"]
    assert dict(m.by_source)["tester"].recall_at_k == 1.0
    assert dict(m.by_source)["real-queries"].recall_at_k == 0.0
    assert EvalMetrics.from_dict(m.as_dict()) == m
    assert source_order(["zz", "spec", "tester", "docs"]) == ["docs", "spec", "tester", "zz"]
    with pytest.raises(ValueError, match="lowercase label"):
        GoldQuestion("x", GoldKind.SEARCH, "q", ("d",), source="Tester Set")
