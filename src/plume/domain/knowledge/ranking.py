"""Reciprocal rank fusion of ranked lists (hybrid search)."""

from collections.abc import Sequence
from dataclasses import dataclass

RRF_K = 60


@dataclass(frozen=True, slots=True)
class Fusion:
    """How hybrid search fuses its dense and full-text rankings (RRF ``k`` and the dense
    list's weight; the text list weighs 1). The default (60, 1) is plain RRF, right for an
    embedder that carries little meaning (the offline hash). With a real embedding model a small
    k and a heavy dense weight keep a clear dense winner that keyword search misses (paraphrased
    questions) above documents that merely match words in both lists."""

    k: int = RRF_K
    dense_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.k < 1 or self.dense_weight <= 0:
            raise ValueError("fusion needs k >= 1 and a positive dense weight")


SEMANTIC_FUSION = Fusion(k=10, dense_weight=5.0)


@dataclass(frozen=True, slots=True)
class FusedRank:
    key: str
    score: float
    ranks: tuple[int | None, ...]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = RRF_K, weights: Sequence[float] | None = None
) -> list[FusedRank]:
    """Fuse rankings (lists of keys, best first). Ties break by best single rank, then key."""
    w = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(w) != len(rankings):
        raise ValueError("one weight per ranking")
    positions: dict[str, list[int | None]] = {}
    for i, ranking in enumerate(rankings):
        for rank, key in enumerate(ranking, start=1):
            slots = positions.setdefault(key, [None] * len(rankings))
            if slots[i] is None:
                slots[i] = rank
    fused = [
        FusedRank(
            key=key,
            score=sum(w[i] / (k + r) for i, r in enumerate(ranks) if r is not None),
            ranks=tuple(ranks),
        )
        for key, ranks in positions.items()
    ]
    return sorted(
        fused,
        key=lambda f: (-f.score, min(r for r in f.ranks if r is not None), f.key),
    )
