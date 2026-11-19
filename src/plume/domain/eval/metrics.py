"""Eval metrics over gold questions."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from plume.domain.eval.gold import GOLD_SOURCES, GoldKind, GoldQuestion, source_order

K = 5
COMBINED = "combined"
GATE_SOURCES = (COMBINED, *GOLD_SOURCES[:2])  # the gate reads combined, docs or spec


@dataclass(frozen=True, slots=True)
class QuestionOutcome:
    qid: str
    kind: GoldKind
    ranked: tuple[str, ...] = ()  # search: retrieved doc ids, best first
    found: bool | None = None  # fact questions
    complete: bool | None = None
    missing_expected: tuple[str, ...] = ()  # expected docs not present in the build at all

    def first_hit_rank(self, expected: Sequence[str]) -> int | None:
        for rank, doc in enumerate(self.ranked, start=1):
            if doc in expected:
                return rank
        return None


FEW_QUESTIONS = 10  # below this, a gold set is a sanity check, not a measurement
FEW_QUESTIONS_NOTE = "Too few questions to measure; a sanity check only."
LEGACY_TOP1 = "citation_hit_rate"  # the old name of top1_rate in stored eval results


def _top1(d: dict[str, Any]) -> float:
    """top1_rate: the share of questions whose first result is an expected one (stored results
    from before the rename call it citation_hit_rate)."""
    return float(d["top1_rate"] if "top1_rate" in d else d[LEGACY_TOP1])


def few_questions_note(questions: int) -> str | None:
    """The quality hint for a gold set too small to measure (None otherwise)."""
    return FEW_QUESTIONS_NOTE if questions < FEW_QUESTIONS else None


@dataclass(frozen=True, slots=True)
class SourceMetrics:
    """Search metrics over the questions of one source (docs or spec), or all of them."""

    recall_at_k: float
    mrr: float
    top1_rate: float
    search_questions: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "top1_rate": self.top1_rate,
            "search_questions": self.search_questions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceMetrics":
        return cls(
            recall_at_k=float(d["recall_at_k"]),
            mrr=float(d["mrr"]),
            top1_rate=_top1(d),
            search_questions=int(d["search_questions"]),
        )


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    recall_at_k: float
    mrr: float
    top1_rate: float
    fact_accuracy: float
    missing_expected: int
    questions: int
    search_questions: int
    fact_questions: int
    k: int = K
    # Per question source, only for sources that have search questions. The top-level search
    # metrics are the combined ones.
    by_source: tuple[tuple[str, SourceMetrics], ...] = ()

    @property
    def combined(self) -> SourceMetrics:
        return SourceMetrics(self.recall_at_k, self.mrr, self.top1_rate, self.search_questions)

    def source(self, name: str) -> SourceMetrics | None:
        """The search metrics of ``docs``, ``spec`` or ``combined`` (None: no such questions).
        Sets written before sources existed count as docs."""
        if name == COMBINED:
            return self.combined
        found = dict(self.by_source).get(name)
        if found is None and name == GOLD_SOURCES[0] and not self.by_source:
            return self.combined if self.search_questions else None
        return found

    def as_dict(self) -> dict[str, Any]:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "top1_rate": self.top1_rate,
            "fact_accuracy": self.fact_accuracy,
            "missing_expected": self.missing_expected,
            "questions": self.questions,
            "search_questions": self.search_questions,
            "fact_questions": self.fact_questions,
            "k": self.k,
            "by_source": {name: m.as_dict() for name, m in self.by_source},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvalMetrics":
        return cls(
            recall_at_k=float(d["recall_at_k"]),
            mrr=float(d["mrr"]),
            top1_rate=_top1(d),
            fact_accuracy=float(d["fact_accuracy"]),
            missing_expected=int(d["missing_expected"]),
            questions=int(d["questions"]),
            search_questions=int(d["search_questions"]),
            fact_questions=int(d["fact_questions"]),
            k=int(d.get("k", K)),
            by_source=tuple(
                (name, SourceMetrics.from_dict(m)) for name, m in (d.get("by_source") or {}).items()
            ),
        )


def _search_metrics(
    questions: Sequence[GoldQuestion], by_id: dict[str, QuestionOutcome], k: int
) -> SourceMetrics:
    hits = rr = top1 = 0.0
    for q in questions:
        rank = by_id[q.qid].first_hit_rank(q.expect_docs)
        if rank is not None and rank <= k:
            hits += 1
            rr += 1 / rank
        if rank == 1:
            top1 += 1
    n = len(questions)
    if not n:
        return SourceMetrics(1.0, 1.0, 1.0, 0)
    return SourceMetrics(round(hits / n, 4), round(rr / n, 4), round(top1 / n, 4), n)


def score(
    questions: Sequence[GoldQuestion], outcomes: Sequence[QuestionOutcome], k: int = K
) -> EvalMetrics:
    by_id = {o.qid: o for o in outcomes}
    if set(by_id) != {q.qid for q in questions}:
        raise ValueError("one outcome per gold question")
    search = [q for q in questions if q.kind is GoldKind.SEARCH]
    facts = [q for q in questions if q.kind is not GoldKind.SEARCH]
    combined = _search_metrics(search, by_id, k)
    by_source = tuple(
        (name, _search_metrics(subset, by_id, k))
        for name in source_order(q.source for q in search)
        if (subset := [q for q in search if q.source == name])
    )
    correct = 0
    for q in facts:
        o = by_id[q.qid]
        if q.kind is GoldKind.PRESENT and o.found is True:
            correct += 1
        if q.kind is GoldKind.ABSENT and o.found is False and o.complete is True:
            correct += 1
    return EvalMetrics(
        recall_at_k=combined.recall_at_k,
        mrr=combined.mrr,
        top1_rate=combined.top1_rate,
        fact_accuracy=round(correct / len(facts), 4) if facts else 1.0,
        missing_expected=sum(len(o.missing_expected) for o in outcomes),
        questions=len(questions),
        search_questions=len(search),
        fact_questions=len(facts),
        k=k,
        by_source=by_source,
    )
