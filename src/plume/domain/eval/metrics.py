"""Eval metrics over gold questions."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from plume.domain.eval.gold import GOLD_SOURCES, GoldKind, GoldQuestion

K = 5
COMBINED = "combined"
GATE_SOURCES = (COMBINED, *GOLD_SOURCES)


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


@dataclass(frozen=True, slots=True)
class SourceMetrics:
    """Search metrics over the questions of one source (docs or spec), or all of them."""

    recall_at_k: float
    mrr: float
    citation_hit_rate: float
    search_questions: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "citation_hit_rate": self.citation_hit_rate,
            "search_questions": self.search_questions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceMetrics":
        return cls(
            recall_at_k=float(d["recall_at_k"]),
            mrr=float(d["mrr"]),
            citation_hit_rate=float(d["citation_hit_rate"]),
            search_questions=int(d["search_questions"]),
        )


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    recall_at_k: float
    mrr: float
    citation_hit_rate: float
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
        return SourceMetrics(
            self.recall_at_k, self.mrr, self.citation_hit_rate, self.search_questions
        )

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
            "citation_hit_rate": self.citation_hit_rate,
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
            citation_hit_rate=float(d["citation_hit_rate"]),
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
        for name in GOLD_SOURCES
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
        citation_hit_rate=combined.citation_hit_rate,
        fact_accuracy=round(correct / len(facts), 4) if facts else 1.0,
        missing_expected=sum(len(o.missing_expected) for o in outcomes),
        questions=len(questions),
        search_questions=len(search),
        fact_questions=len(facts),
        k=k,
        by_source=by_source,
    )
