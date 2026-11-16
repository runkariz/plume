"""Release gate: stop a build that is worse than the live release, or below the floor."""

from dataclasses import dataclass

from plume.domain.eval.metrics import COMBINED, GATE_SOURCES, EvalMetrics


@dataclass(frozen=True, slots=True)
class GatePolicy:
    min_recall: float = 0.6
    min_fact_accuracy: float = 1.0
    max_drop: float = 0.05  # allowed fall of recall@k / MRR vs the live release
    allow_missing_expected: bool = False
    # Which questions the recall floor reads: combined, docs or spec. A set without questions of
    # that source falls back to combined.
    source: str = COMBINED

    def __post_init__(self) -> None:
        if self.source not in GATE_SOURCES:
            raise ValueError(f"gate source must be one of {', '.join(GATE_SOURCES)}")


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    reasons: tuple[str, ...]

    @property
    def message(self) -> str:
        if self.passed:
            return "Quality gate passed."
        return "Quality gate failed: " + "; ".join(self.reasons)


def decide(
    policy: GatePolicy, staged: EvalMetrics, live: EvalMetrics | None = None
) -> GateDecision:
    reasons: list[str] = []
    floor = staged.source(policy.source)
    label = "" if policy.source == COMBINED else f" ({policy.source} questions)"
    if floor is None or not floor.search_questions:
        floor, label = staged.combined, ""
    if floor.recall_at_k < policy.min_recall:
        reasons.append(
            f"recall@{staged.k}{label} {floor.recall_at_k:.2f} is below the floor "
            f"{policy.min_recall:.2f}"
        )
    if staged.fact_accuracy < policy.min_fact_accuracy:
        reasons.append(
            f"fact accuracy {staged.fact_accuracy:.2f} is below {policy.min_fact_accuracy:.2f}"
        )
    if staged.missing_expected and not policy.allow_missing_expected:
        reasons.append(f"{staged.missing_expected} expected document(s) are missing from the build")
    if live is not None:
        # Combined, and each source separately when the set has more than one.
        sources = [COMBINED] + (
            [n for n, _ in staged.by_source] if len(staged.by_source) > 1 else []
        )
        for src in sources:
            new_m, old_m = staged.source(src), live.source(src)
            if new_m is None or old_m is None or not old_m.search_questions:
                continue
            tail = "" if src == COMBINED else f" ({src} questions)"
            for name, new, old in (
                (f"recall@{staged.k}{tail}", new_m.recall_at_k, old_m.recall_at_k),
                (f"MRR{tail}", new_m.mrr, old_m.mrr),
            ):
                if old - new > policy.max_drop + 1e-9:
                    reasons.append(
                        f"{name} fell from {old:.2f} to {new:.2f} (more than {policy.max_drop:.2f})"
                    )
    return GateDecision(passed=not reasons, reasons=tuple(reasons))
