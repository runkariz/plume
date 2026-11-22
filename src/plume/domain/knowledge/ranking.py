"""Reciprocal rank fusion of ranked lists (hybrid search)."""

import re
from collections.abc import Callable, Sequence
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


# Words for a non-production environment, which APIs name differently (Shopware has no
# sandbox, but documents a staging instance). Used only to expand the full-text query.
_ENV_TERMS = ("sandbox", "staging", "test environment", "test account", "test mode", "test shop")
_ENV_QUERY = re.compile(
    r"\b(sandbox(es)?|staging|test(ing)? (environment|account|mode|shop|store|instance))\b",
    re.IGNORECASE,
)


def expand_text_query(query: str, documented: Callable[[str], bool] = lambda _w: True) -> str:
    """The full-text query with the environment synonyms a question does not already use,
    when it asks about one the API's documents never mention (``documented``): "does
    Shopware have a sandbox" also matches "staging". An API that names its sandbox keeps the
    question as asked."""
    m = _ENV_QUERY.search(query)
    if m is None or documented(m.group(0).lower()):
        return query
    low = query.lower()
    extra = [t for t in _ENV_TERMS if t not in low]
    return f"{query} {' '.join(extra)}" if extra else query
