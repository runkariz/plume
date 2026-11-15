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
