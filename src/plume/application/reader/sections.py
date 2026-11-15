"""Package sections exposed as stored (never derived): auth schemes, triggers, the icon."""

from dataclasses import dataclass
from typing import Any

from plume.application.errors import NotFoundError
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.search_index import SearchIndex
from plume.application.reader.dto import BuildRef
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge.asset import ICON, Asset
from plume.domain.knowledge.document import Document, DocumentKind

WEBHOOKS_TAG = "webhooks"
MAX_SECTION_ITEMS = 1000


def _ref(r: ResolvedBuild) -> BuildRef:
    return BuildRef(r.api.api_id.value, r.build.build_id.value, r.tag, r.docs_as_of)


@dataclass(frozen=True, slots=True)
class SectionCounts:
    auth: int
    triggers: int
    webhook_endpoints: int


class PackageSections:
    def __init__(
        self,
        resolver: BuildResolver,
        index: SearchIndex,
        documents: DocumentRepo,
        assets: AssetRepo,
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._documents = documents
        self._assets = assets

    def _docs(self, r: ResolvedBuild, kind: DocumentKind) -> list[Document]:
        build = r.build.build_id
        items, _ = self._index.browse(build, (kind,), None, MAX_SECTION_ITEMS, 0)
        docs = [self._documents.get_document(build, s.doc_id) for s in items]
        return [d for d in docs if d is not None]

    def counts(self, api: str, version: str | None = None) -> SectionCounts:
        r = self._resolver.resolve(api, version)
        counts = self._index.counts(r.build.build_id)
        _, webhooks = self._index.browse(
            r.build.build_id, (DocumentKind.ENDPOINT,), None, 1, 0, tag=WEBHOOKS_TAG
        )
        return SectionCounts(counts.get("auth", 0), counts.get("trigger", 0), webhooks)

    def auth_schemes(self, api: str, version: str | None = None) -> tuple[BuildRef, list[Document]]:
        r = self._resolver.resolve(api, version)
        return _ref(r), self._docs(r, DocumentKind.AUTH)

    def auth_scheme(
        self, api: str, scheme_id: str, version: str | None = None
    ) -> tuple[BuildRef, Document]:
        ref, docs = self.auth_schemes(api, version)
        for d in docs:
            if scheme_id in (d.doc_id, d.source_id):
                return ref, d
        raise NotFoundError(f"{api} has no auth scheme {scheme_id!r}")

    def triggers(self, api: str, version: str | None = None) -> tuple[BuildRef, list[Document]]:
        r = self._resolver.resolve(api, version)
        return _ref(r), self._docs(r, DocumentKind.TRIGGER)

    def trigger(self, api: str, key: str, version: str | None = None) -> tuple[BuildRef, Document]:
        r = self._resolver.resolve(api, version)
        if key.startswith("trigger:"):
            doc = self._documents.get_document(r.build.build_id, key)
            if doc is not None:
                return _ref(r), doc
        for d in self._docs(r, DocumentKind.TRIGGER):
            if key == d.source_id:
                return _ref(r), d
        raise NotFoundError(f"{api} has no trigger {key!r}")

    def icon(self, api: str, version: str | None = None) -> tuple[BuildRef, Asset | None]:
        r = self._resolver.resolve(api, version)
        return _ref(r), self._assets.get(r.build.build_id, ICON)


def _obj(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def scheme_view(d: Document) -> dict[str, Any]:
    """Fields read straight from the stored auth JSON (verbatim values, None when absent)."""
    raw = dict(d.raw or {})
    scheme: dict[str, Any] = _obj(raw.get("scheme")) or {}
    variables = _obj(raw.get("variables_schema"))
    props: dict[str, Any] = (_obj(variables.get("properties")) or {}) if variables else {}
    required = set(variables.get("required") or []) if variables else set()
    return {
        "id": scheme.get("id") or d.source_id or d.doc_id,
        "doc_id": d.doc_id,
        "name": d.title,
        "type": scheme.get("authorizationType"),
        "grant_type": scheme.get("grantType"),
        "header_name": scheme.get("headerName"),
        "query_param": scheme.get("codeQueryParamName"),
        "scopes": [
            {"scope": s.get("scope"), "description": s.get("description")}
            for s in scheme.get("scopes", []) or []
            if isinstance(s, dict)
        ],
        "variables": [
            {
                "name": name,
                "description": spec.get("description") if isinstance(spec, dict) else None,
                "type": spec.get("type") if isinstance(spec, dict) else None,
                "required": name in required,
            }
            for name, spec in props.items()
        ],
        "setup_steps": scheme.get("setupSteps"),
        "token_lifetime": scheme.get("tokenLifetime"),
        "test_url": scheme.get("testUrl"),
        "scheme": scheme,
        "variables_schema": variables,
        "file": raw.get("file"),
    }


def trigger_view(d: Document) -> dict[str, Any]:
    raw = dict(d.raw or {})
    return {
        "key": d.source_id or raw.get("key"),
        "doc_id": d.doc_id,
        "title": d.title,
        "description": raw.get("description"),
        "resource": raw.get("resource"),
        "delivery": raw.get("delivery"),
        "source_url": d.source_url,
        "event": raw,
    }
