"""Eval metrics over gold questions."""

from collections.abc import Sequence
from dataclasses import dataclass

from plume.domain.eval.gold import GoldKind, GoldQuestion

K = 5


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

    def as_dict(self) -> dict[str, float | int]:
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
        }

    @classmethod
    def from_dict(cls, d: dict[str, float | int]) -> "EvalMetrics":
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
        )


def score(
    questions: Sequence[GoldQuestion], outcomes: Sequence[QuestionOutcome], k: int = K
) -> EvalMetrics:
    by_id = {o.qid: o for o in outcomes}
    if set(by_id) != {q.qid for q in questions}:
        raise ValueError("one outcome per gold question")
    search = [q for q in questions if q.kind is GoldKind.SEARCH]
    facts = [q for q in questions if q.kind is not GoldKind.SEARCH]
    hits = rr = top1 = 0.0
    for q in search:
        rank = by_id[q.qid].first_hit_rank(q.expect_docs)
        if rank is not None and rank <= k:
            hits += 1
            rr += 1 / rank
        if rank == 1:
            top1 += 1
    correct = 0
    for q in facts:
        o = by_id[q.qid]
        if q.kind is GoldKind.PRESENT and o.found is True:
            correct += 1
        if q.kind is GoldKind.ABSENT and o.found is False and o.complete is True:
            correct += 1
    n_s = len(search) or 1
    return EvalMetrics(
        recall_at_k=round(hits / n_s, 4) if search else 1.0,
        mrr=round(rr / n_s, 4) if search else 1.0,
        citation_hit_rate=round(top1 / n_s, 4) if search else 1.0,
        fact_accuracy=round(correct / len(facts), 4) if facts else 1.0,
        missing_expected=sum(len(o.missing_expected) for o in outcomes),
        questions=len(questions),
        search_questions=len(search),
        fact_questions=len(facts),
        k=k,
    )
