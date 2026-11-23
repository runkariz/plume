"""Match a concrete HTTP call against documented endpoint paths."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from plume.domain.knowledge.document import normalize_endpoint_path

_PARAM = re.compile(r"^\{[^/{}]+\}$")


def _segments(path: str) -> list[str]:
    return [s for s in path.split("?", 1)[0].strip("/").split("/") if s]


def path_matches(template: str, path: str) -> bool:
    """``/orders/{id}.json`` matches ``/orders/42.json``; ``{version}`` matches any version; a
    variable inside a segment matches there too (``act_{AD_ACCOUNT_ID}`` matches ``act_123``,
    ``{a}-{b}`` matches ``1-2``)."""
    t, p = _segments(template), _segments(path)
    if len(t) != len(p):
        return False
    for ts, ps in zip(t, p, strict=True):
        if ts == ps or _PARAM.fullmatch(ts):
            continue
        if "{" in ts and _segment_pattern(ts).fullmatch(ps):
            continue
        return False
    return True


_VAR = re.compile(r"\{[^/{}]+\}")


def _segment_pattern(segment: str) -> re.Pattern[str]:
    """A templated segment as a pattern: its literal text exactly, each {variable} one or more
    characters other than "/"."""
    parts = _VAR.split(segment)
    return re.compile("[^/]+".join(re.escape(x) for x in parts))


def specificity(template: str) -> int:
    """More literal text = more specific (preferred when several templates match): a literal
    segment counts 2, a segment that mixes text and a variable (act_{id}) 1, a variable 0."""
    return sum(2 if "{" not in s else 0 if _PARAM.fullmatch(s) else 1 for s in _segments(template))


def normalize_call_path(path: str, known_versions: tuple[str, ...] = ()) -> str:
    stripped = re.sub(r"^[a-z]+://[^/]+", "", path.strip())
    return normalize_endpoint_path(stripped, known_versions)


# The loader's environments guide: an environment per line with its base URL ("- production:
# https://apigw.trendyol.com/integration/ecgw (default)"), then its other servers indented
# ("  - api_3: https://apim.ebay.com/commerce/media/v1_beta"). A server whose URL is the base URL
# (usually `api`) is not listed again: the base URL stands for it.
_ENV_LINE = re.compile(r"^-\s+([^:\n]+?)(?:\s+\([^)]*\))?:\s+(https?://[^\s,]+)")
_SUB_LINE = re.compile(r"^\s+-\s+([A-Za-z0-9_]+):\s+(https?://[^\s,]+)")
_SERVER_REF = re.compile(r"^\{\{\s*app_env\.servers\.([A-Za-z0-9_]+)\s*\}\}")
_TEMPLATE = re.compile(r"^(\{\{[^{}]+\}\}|\{[^{}]+\})$")


@dataclass(frozen=True, slots=True)
class ServerBase:
    key: str  # the server (api_3), or the environment for its base URL (production)
    url: str
    host: str  # lower case; may be a template ({{app_env.vars.host}})
    prefix: str  # the URL's path, no trailing slash ("/integration/ecgw", "/stores/{{...}}")
    # an environment's base URL: the servers it does NOT stand for (listed with their own URL)
    others: frozenset[str] | None = None

    def serves(self, server: str | None) -> bool:
        """Whether an endpoint of this server (from its url; None: not named) is called here."""
        if server is None:
            return True
        return server not in self.others if self.others is not None else server == self.key

    @property
    def label(self) -> str:
        return (
            f"{self.key}: {self.url}" if self.others is None else f"{self.key} base URL: {self.url}"
        )


def _base(key: str, raw: str, others: frozenset[str] | None) -> ServerBase | None:
    url = raw.rstrip(".;)")
    parsed = urlsplit(url)
    prefix = parsed.path.rstrip("/")
    return ServerBase(key.strip(), url, parsed.netloc.lower(), prefix, others) if prefix else None


def server_bases(environments_text: str) -> list[ServerBase]:
    """Every environment's servers whose URL carries a path (eBay api_3 = https://apim.ebay.com/
    commerce/media/v1_beta; Trendyol Export Center's base https://apigw.trendyol.com/integration/
    ecgw, stage too): endpoints of those servers are stored without it."""
    envs: list[tuple[bool, str, str, list[tuple[str, str]]]] = []  # default?, name, url, subs
    for line in environments_text.splitlines():
        if m := _ENV_LINE.match(line):
            envs.append(("(default)" in line, m.group(1), m.group(2), []))
        elif (m := _SUB_LINE.match(line)) and envs:
            envs[-1][3].append((m.group(1), m.group(2)))
    # the default environment first: a relative path reports its base URL
    envs.sort(key=lambda e: not e[0])
    out: list[ServerBase] = []
    for _, name, url, subs in envs:
        listed = frozenset(k for k, _ in subs)
        out += [b for b in [_base(name, url, listed), *(_base(k, u, None) for k, u in subs)] if b]
    return out


def endpoint_server(url: str) -> str | None:
    """The server an endpoint's url names ({{app_env.servers.api_3}}/video -> api_3)."""
    m = _SERVER_REF.match(url.strip())
    return m.group(1) if m else None


def _same_segment(template: str, given: str) -> bool:
    return bool(_TEMPLATE.match(template)) or template.lower() == given.lower()


def without_server_base(path: str, bases: list[ServerBase]) -> list[tuple[ServerBase, str]]:
    """The call path with a server's base path taken off, per server it starts with: the path a
    developer calls (/integration/ecgw/v3/123/packages, or the full URL) as stored
    (/v3/123/packages). A template segment of the base ({{app_env.vars.store_hash}}) matches any
    one segment; a full URL counts only for that server's host (any host for a template)."""
    given = path.strip()
    parsed = urlsplit(given) if re.match(r"^[a-z]+://", given) else None
    host = parsed.netloc.lower() if parsed else None
    rest = (parsed.path or "/") if parsed else given.split("?", 1)[0]
    query = (parsed.query if parsed else given.partition("?")[2]) or ""
    segs = [x for x in rest.split("/") if x]
    out: list[tuple[ServerBase, str]] = []
    for b in bases:
        if host is not None and host != b.host and "{" not in b.host:
            continue
        pre = [x for x in b.prefix.split("/") if x]
        if len(segs) < len(pre) or not all(map(_same_segment, pre, segs)):
            continue
        tail = "/" + "/".join(segs[len(pre) :])
        out.append((b, tail + (f"?{query}" if query else "")))
    return out


@dataclass(frozen=True, slots=True)
class Environment:
    """One environment of the environments guide: its base URL and the servers listed with their
    own URL (a server not listed is served by the base URL)."""

    name: str
    base: str
    servers: tuple[tuple[str, str], ...]

    def url_of(self, server: str | None) -> str:
        return dict(self.servers).get(server or "", self.base)


def environments_of(environments_text: str) -> list[Environment]:
    envs: list[tuple[str, str, list[tuple[str, str]]]] = []
    for line in environments_text.splitlines():
        if m := _ENV_LINE.match(line):
            envs.append((m.group(1), m.group(2).rstrip(".;)"), []))
        elif (m := _SUB_LINE.match(line)) and envs:
            envs[-1][2].append((m.group(1), m.group(2).rstrip(".;)")))
    return [Environment(n, b, tuple(s)) for n, b, s in envs]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def host_problem(call: str, server: str | None, envs: list[Environment]) -> tuple[str, str] | None:
    """A full-URL call on a host that does not serve the endpoint: ("other_server", why) when the
    host is another server of this API (Meta's ads-api / mcp hosts for a graph endpoint), else
    ("unknown_host", why). None: a relative path, a matching host, or hosts Plume cannot check
    (a templated host such as {{app_env.vars.host}}, no environments)."""
    given = call.strip()
    if not re.match(r"^[a-z]+://", given, re.I) or not envs:
        return None
    host = _host(given)
    expected = {_host(e.url_of(server)) for e in envs}
    if not host or host in expected or any(not h or "{" in h for h in expected):
        return None
    owners: dict[str, str] = {}
    for e in envs:
        owners.setdefault(_host(e.base), f"the {e.name} base URL")
        for key, url in e.servers:
            owners.setdefault(_host(url), f"the {key} server")
    where = ", ".join(sorted(expected))
    on = f"the {server} server" if server else "the base URL"
    if host in owners:
        return "other_server", f"{host} is {owners[host]}; this endpoint is on {on} ({where})"
    return "unknown_host", f"{host} is not a server of this API for this endpoint ({on}: {where})"
