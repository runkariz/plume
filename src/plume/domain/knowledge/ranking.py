"""Reciprocal rank fusion of ranked lists (hybrid search)."""

from collections.abc import Sequence
from dataclasses import dataclass

RRF_K = 60


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
