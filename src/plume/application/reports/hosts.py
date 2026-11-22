"""The hosts an API's own documents name (its servers, docs, templates like {shop}.myshopify
.com): a reported URL on any other host is not the API's and is redacted."""

import re
import threading
from collections import OrderedDict
from collections.abc import Callable

from plume.application.errors import ApplicationError
from plume.application.ports.document_repo import DocumentRepo
from plume.application.reader.resolve import BuildResolver
from plume.domain.shared.ids import BuildId

_HOST = re.compile(r"\bhttps?://([^/\s\"'<>)\]`,;]+)", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\\\{\\\{.*?\\\}\\\}|\\\{[^}]*\\\}")
MAX_BUILDS = 16
_Hosts = tuple[frozenset[str], tuple[tuple[re.Pattern[str], str], ...]]  # exact, templates


class ApiHosts:
    def __init__(self, resolver: BuildResolver, documents: DocumentRepo) -> None:
        self._resolver = resolver
        self._documents = documents
        self._cache: OrderedDict[str, _Hosts] = OrderedDict()
        self._lock = threading.Lock()

    def of(self, api: str) -> Callable[[str], str | None]:
        """host -> how it may be written (itself, or the documented template it matches), or
        None when the API's documents never name it. Read lazily: only for a text with a URL."""
        build: list[str] = []

        def known(host: str) -> str | None:
            if not build:
                try:
                    build.append(self._resolver.resolve(api).build.build_id.value)
                except ApplicationError:
                    return None
            exact, templates = self._hosts(build[0])
            h = host.lower().removeprefix("www.")
            if h in exact:
                return h
            return next((t for rx, t in templates if rx.fullmatch(h)), None)

        return known

    def _hosts(self, build: str) -> _Hosts:
        with self._lock:
            if build in self._cache:
                self._cache.move_to_end(build)
                return self._cache[build]
        exact: set[str] = set()
        templates: dict[str, re.Pattern[str]] = {}
        for d in self._documents.list_documents(BuildId(build)):
            url = d.raw.get("url") if isinstance(d.raw, dict) else None
            for host in _HOST.findall(f"{d.text} {url if isinstance(url, str) else ''}"):
                h = host.lower().split("@")[-1].split(":")[0].removeprefix("www.")
                if "{" in h:
                    rx = _PLACEHOLDER.sub(r"[a-z0-9-]+", re.escape(h))
                    templates[h] = re.compile(rx)
                elif h:
                    exact.add(h)
        found = (frozenset(exact), tuple((rx, t) for t, rx in sorted(templates.items())))
        with self._lock:
            self._cache[build] = found
            while len(self._cache) > MAX_BUILDS:
                self._cache.popitem(last=False)
        return found
