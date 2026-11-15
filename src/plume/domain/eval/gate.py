"""Release gate: stop a build that is worse than the live release, or below the floor."""

from dataclasses import dataclass

from plume.domain.eval.metrics import EvalMetrics


@dataclass(frozen=True, slots=True)
class GatePolicy:
    min_recall: float = 0.6
    min_fact_accuracy: float = 1.0
    max_drop: float = 0.05  # allowed fall of recall@k / MRR vs the live release
    allow_missing_expected: bool = False


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
    if staged.recall_at_k < policy.min_recall:
        reasons.append(
            f"recall@{staged.k} {staged.recall_at_k:.2f} is below the floor {policy.min_recall:.2f}"
        )
    if staged.fact_accuracy < policy.min_fact_accuracy:
        reasons.append(
            f"fact accuracy {staged.fact_accuracy:.2f} is below {policy.min_fact_accuracy:.2f}"
        )
    if staged.missing_expected and not policy.allow_missing_expected:
        reasons.append(f"{staged.missing_expected} expected document(s) are missing from the build")
    if live is not None:
        for name, new, old in (
            (f"recall@{staged.k}", staged.recall_at_k, live.recall_at_k),
            ("MRR", staged.mrr, live.mrr),
        ):
            if old - new > policy.max_drop + 1e-9:
                reasons.append(
                    f"{name} fell from {old:.2f} to {new:.2f} (more than {policy.max_drop:.2f})"
                )
    return GateDecision(passed=not reasons, reasons=tuple(reasons))
