"""Keep a documentation page's endpoint next to the page in the top results.

Knowledge-export page guides often rank first for a question (they carry the page's prose), and
can push the endpoint the question is about out of the top-k. Pages are not demoted: for every
page in the top-k whose endpoints are all missing from it, the best-ranked of its endpoints
from the rest of the pool moves in right after the page, and the lowest-ranked result that is
neither a page nor such an endpoint makes room.
"""

from collections.abc import Callable, Sequence

PAGE_PREFIX = "guide:page-"


def is_page(doc_id: str) -> bool:
    return doc_id.startswith(PAGE_PREFIX)


def pair_pages_with_endpoints(
    ranked: Sequence[str],
    k: int,
    endpoints_of: Callable[[str], Sequence[str]],
) -> list[str]:
    """`ranked` reordered (same ids) so each page in the top-`k` has one of its endpoints there
    too, when the pool holds one."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    protected: set[str] = {d for d in top if is_page(d)}
    for page in [d for d in top if is_page(d)]:
        endpoints = set(endpoints_of(page))
        if not endpoints:
            continue
        present = [d for d in top if d in endpoints]
        if present:
            protected.update(present)
            continue
        candidate = next((d for d in rest if d in endpoints), None)
        victim = next((d for d in reversed(top) if d not in protected), None)
        if candidate is None or victim is None:
            continue
        top.remove(victim)
        top.insert(top.index(page) + 1, candidate)
        rest.remove(candidate)
        rest.insert(0, victim)
        protected.add(candidate)
    return top + rest


def lift_operation_endpoints(
    ranked: Sequence[str], k: int, owner_of: Callable[[str], str | None]
) -> list[str]:
    """`ranked` reordered (same ids) so a per-operation model in the top-`k` (Mirakl's
    `a02-response-200-...`: a piece of PUT /api/account's response) has its endpoint just before
    it, when the pool holds that endpoint. The pieces stay; the endpoint the question is about
    comes first."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    placed: set[str] = set()
    for doc in list(top):
        if doc not in top:  # pushed out by an earlier lift
            continue
        owner = owner_of(doc)
        if owner is None or owner in placed:
            continue
        placed.add(owner)
        if owner in top:
            if top.index(owner) > top.index(doc):
                top.remove(owner)
                top.insert(top.index(doc), owner)
            continue
        if owner not in rest:
            continue
        rest.remove(owner)
        top.insert(top.index(doc), owner)
        rest.insert(0, top.pop())
    return top + rest


def pair_units_with_endpoints(
    ranked: Sequence[str],
    k: int,
    linked_of: Callable[[str], Sequence[str]],
    wider: Callable[[], Sequence[str]],
) -> list[str]:
    """`ranked` reordered so a knowledge unit in the top-`k` that names its endpoints
    (``endpointIds``) has one of them right after it, like a page does.

    A unit's question ("which scope does the Logistic Centers API need?") is about its endpoint,
    but the unit's prose outranks the endpoint's thin text. The endpoint comes from the pool, or
    else from `wider` (the endpoints ranked for the query; asked once, only when needed). The
    result that makes room is the lowest-ranked one below the unit that is neither an endpoint
    nor a unit/page with links: nothing ranked above the unit moves out, no endpoint is evicted.
    Units without links leave the order unchanged."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    anchors = [d for d in top if not is_page(d) and linked_of(d)]
    if not anchors:
        return top + rest
    protected = set(anchors) | {d for d in top if d.startswith("endpoint:") or is_page(d)}
    extra: list[str] | None = None
    for unit in anchors:
        endpoints = set(linked_of(unit))
        present = [d for d in top if d in endpoints]
        if present:
            continue
        candidate = next((d for d in rest if d in endpoints), None)
        if candidate is None:
            if extra is None:
                extra = list(wider())
            candidate = next((d for d in extra if d in endpoints), None)
        position = top.index(unit)
        victim = next(
            (d for d in reversed(top) if d not in protected and top.index(d) > position), None
        )
        if candidate is None or victim is None:
            continue
        top.remove(victim)
        top.insert(top.index(unit) + 1, candidate)
        if candidate in rest:
            rest.remove(candidate)
        rest.insert(0, victim)
        protected.add(candidate)
    return top + rest


MIN_ENDPOINTS = 2


def keep_endpoints(ranked: Sequence[str], k: int, minimum: int = MIN_ENDPOINTS) -> list[str]:
    """At least ``minimum`` endpoints in the top-k when the pool has them: the best-ranked
    endpoints below the top-k replace its lowest-ranked other results (which move to the front
    of the rest); the top-k keeps the pool's order. Knowledge units outnumber endpoints several
    times over, and a question about an operation was otherwise answered by guides alone."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    have = sum(1 for d in top if d.startswith("endpoint:"))
    for candidate in [d for d in rest if d.startswith("endpoint:")]:
        if have >= min(minimum, k):
            break
        victim = next((d for d in reversed(top) if not d.startswith("endpoint:")), None)
        if victim is None:
            break
        top[top.index(victim)] = candidate
        rest.remove(candidate)
        rest.insert(0, victim)
        have += 1
    position = {d: i for i, d in enumerate(ranked)}
    return sorted(top, key=position.__getitem__) + rest
