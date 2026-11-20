"""Match a concrete HTTP call against documented endpoint paths."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

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


# The loader's environments guide: "- production: https://api.ebay.com (default)" and
# "  - api_3: https://apim.ebay.com/commerce/media/v1_beta" (a server per line).
_SERVER_LINE = re.compile(
    r"^\s*-\s+([^:\n]+?)(?:\s+\([^)]*\))?:\s+(https?://[^\s,]+)", re.MULTILINE
)
_SERVER_REF = re.compile(r"^\{\{\s*app_env\.servers\.([A-Za-z0-9_]+)\s*\}\}")


@dataclass(frozen=True, slots=True)
class ServerBase:
    key: str  # the server's name in app.json (api_3), or the environment's for a baseUrl
    url: str
    host: str
    prefix: str  # the URL's path, without a trailing slash ("/commerce/media/v1_beta")


def server_bases(environments_text: str) -> list[ServerBase]:
    """The servers whose base URL carries a path (eBay api_3 = https://apim.ebay.com/commerce/
    media/v1_beta): endpoints of that server are stored without it."""
    out: list[ServerBase] = []
    for key, raw in _SERVER_LINE.findall(environments_text):
        url = raw.rstrip(".;)")
        parsed = urlsplit(url)
        prefix = parsed.path.rstrip("/")
        if prefix and "{" not in prefix:
            out.append(ServerBase(key.strip(), url, parsed.netloc.lower(), prefix))
    return out


def endpoint_server(url: str) -> str | None:
    """The server an endpoint's url names ({{app_env.servers.api_3}}/video -> api_3)."""
    m = _SERVER_REF.match(url.strip())
    return m.group(1) if m else None


def without_server_base(path: str, bases: list[ServerBase]) -> list[tuple[ServerBase, str]]:
    """The call path with a server's base path taken off, per server it starts with: the path a
    developer calls (/commerce/media/v1_beta/video, or the full URL) as stored (/video). A full
    URL counts only for its own host."""
    given = path.strip()
    parsed = urlsplit(given) if re.match(r"^[a-z]+://", given) else None
    host = parsed.netloc.lower() if parsed else None
    rest = (parsed.path or "/") if parsed else given
    if parsed and parsed.query:
        rest += "?" + parsed.query
    out: list[tuple[ServerBase, str]] = []
    for b in bases:
        if host is not None and host != b.host:
            continue
        low = rest.lower()
        if (
            low == b.prefix.lower()
            or low.startswith(b.prefix.lower() + "/")
            or low.startswith(b.prefix.lower() + "?")
        ):
            out.append((b, rest[len(b.prefix) :] or "/"))
    return out
