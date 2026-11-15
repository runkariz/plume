"""Readable names for bundler-generated model titles.

Some vendors publish OpenAPI bundles whose inline schemas are titled
``<OperationId>_(Request|Response)[_<status>][_<Field>_<Path>]`` (e.g.
``A01_Response_200_DefaultBillingInformation_CorporateInformation``). The display name is the last
path segment ("Corporate Information"), with its parent ("Default Billing Information / Corporate
Information") when the last segment alone names more than one structure. Roots (no path) are
named after the operation ("A01 response 200"). Other titles are kept as they are.
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

_BUNDLED = re.compile(
    r"^(?P<op>[A-Za-z][A-Za-z0-9]*)_(?P<kind>Request|Response)(?:_(?P<status>\d{3}))?"
    r"(?:_(?P<path>[A-Za-z0-9_]+))?$"
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


@dataclass(frozen=True, slots=True)
class BundledTitle:
    operation: str
    kind: str  # request | response
    status: str | None
    path: tuple[str, ...]

    @property
    def is_root(self) -> bool:
        return not self.path


def parse_bundled_title(title: str) -> BundledTitle | None:
    m = _BUNDLED.fullmatch(title.strip())
    if m is None:
        return None
    path = tuple(p for p in (m["path"] or "").split("_") if p)
    return BundledTitle(m["op"], m["kind"].lower(), m["status"], path)


def humanize(segment: str) -> str:
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in _CAMEL.split(segment))


def display_names(entries: Iterable[tuple[str, str, str | None]]) -> dict[str, str]:
    """``(doc_id, title, shape)`` -> display name per doc id (only for bundler titles)."""
    parsed: list[tuple[str, BundledTitle, str]] = []
    shapes_by_leaf: dict[str, set[str]] = defaultdict(set)
    for doc_id, title, shape in entries:
        bt = parse_bundled_title(title)
        if bt is None:
            continue
        parsed.append((doc_id, bt, shape or doc_id))
        if bt.path:
            shapes_by_leaf[bt.path[-1].lower()].add(shape or doc_id)
    out: dict[str, str] = {}
    for doc_id, bt, _ in parsed:
        if bt.is_root:
            out[doc_id] = f"{bt.operation} {bt.kind}" + (f" {bt.status}" if bt.status else "")
            continue
        leaf = humanize(bt.path[-1])
        ambiguous = len(shapes_by_leaf[bt.path[-1].lower()]) > 1
        if ambiguous and len(bt.path) > 1:
            out[doc_id] = f"{humanize(bt.path[-2])} / {leaf}"
        else:
            out[doc_id] = leaf
    return out
