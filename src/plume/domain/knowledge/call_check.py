"""Match a concrete HTTP call against documented endpoint paths."""

import re

from plume.domain.knowledge.document import normalize_endpoint_path

_PARAM = re.compile(r"^\{[^/{}]+\}$")


def _segments(path: str) -> list[str]:
    return [s for s in path.split("?", 1)[0].strip("/").split("/") if s]


def path_matches(template: str, path: str) -> bool:
    """``/orders/{id}.json`` matches ``/orders/42.json``; ``{version}`` matches any version."""
    t, p = _segments(template), _segments(path)
    if len(t) != len(p):
        return False
    for ts, ps in zip(t, p, strict=True):
        if ts == ps or _PARAM.fullmatch(ts):
            continue
        # A templated segment with a suffix, e.g. "{product_id}.json" vs "42.json".
        m = re.fullmatch(r"\{[^/{}]+\}(\.[A-Za-z0-9]+)", ts)
        if m and ps.endswith(m.group(1)) and len(ps) > len(m.group(1)):
            continue
        return False
    return True


def specificity(template: str) -> int:
    """More literal segments = more specific (preferred when several templates match)."""
    return sum(1 for s in _segments(template) if "{" not in s)


def normalize_call_path(path: str, known_versions: tuple[str, ...] = ()) -> str:
    stripped = re.sub(r"^[a-z]+://[^/]+", "", path.strip())
    return normalize_endpoint_path(stripped, known_versions)
