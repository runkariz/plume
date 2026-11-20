"""Package sections exposed as stored (never derived): auth schemes, triggers, the icon."""

import re
from dataclasses import dataclass
from typing import Any

from plume.application.errors import NotFoundError
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.search_index import FactQuery, SearchIndex
from plume.application.reader.dto import BuildRef
from plume.application.reader.links import scope_endpoints
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge import package_warnings, rate_limits
from plume.domain.knowledge.asset import ICON, Asset
from plume.domain.knowledge.document import (
    TRIGGER_PAYLOAD_KEY,
    Document,
    DocumentKind,
    FieldLocation,
)
from plume.domain.knowledge.fact import FactKind
from plume.domain.knowledge.package_warnings import AUTH as AUTH_SECTION
from plume.domain.knowledge.package_warnings import PackageWarning

WEBHOOKS_TAG = "webhooks"
MAX_AUTH_GUIDES = 4
# query / header parameters that carry a request signature
SIGNATURE_PARAMS = ("sign", "signature", "x-signature", "x-sign", "sig", "hmac")
_SIGN_WORD = re.compile(r"\b(sign|signs|signed|signing|signature\w*|hmac)\b", re.IGNORECASE)
_WEBHOOK_WORD = re.compile(r"\bwebhooks?\b", re.IGNORECASE)
_AUTH_WORD = re.compile(
    r"\b(auth\w*|access token\w*|api keys?|credentials?|oauth\w*)\b", re.IGNORECASE
)
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
        facts: FactQuery | None = None,
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._documents = documents
        self._assets = assets
        self._facts = facts

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

    def _app_raw(self, r: ResolvedBuild) -> dict[str, Any]:
        apps = self._docs(r, DocumentKind.APP)
        return dict(apps[0].raw or {}) if apps else {}

    def rate_limits(self, api: str, version: str | None = None) -> list[dict[str, Any]]:
        """app.json rateLimits[] verbatim (empty when the package states none)."""
        r = self._resolver.resolve(api, version)
        return rate_limits.groups(self._app_raw(r).get("app"))

    def package_warnings(
        self, api: str, version: str | None = None
    ) -> list[package_warnings.PackageWarning]:
        """manifest.json warnings of the build's package (all codes; maintainer view)."""
        r = self._resolver.resolve(api, version)
        return package_warnings.parse(self._app_raw(r).get("package_warnings"))

    def notices(
        self, api: str, section: str | None = None, version: str | None = None
    ) -> list[dict[str, Any]]:
        """User-facing notices for the package warnings Plume knows ({code, section, text,
        doc_ids}); auth notices name and link the API's auth / signing guides."""
        r = self._resolver.resolve(api, version)
        warnings = package_warnings.parse(self._app_raw(r).get("package_warnings"))
        has_auth = any(w.code in package_warnings.WITH_AUTH for w in warnings) and bool(
            self._index.browse(r.build.build_id, (DocumentKind.AUTH,), None, 1, 0)[0]
        )
        auth_codes = [
            w for w in warnings if package_warnings.KNOWN.get(w.code, ("",))[0] == AUTH_SECTION
        ]
        guides: tuple[tuple[str, str], ...] | None = None
        signed: bool | None = None
        if auth_codes and section in (None, AUTH_SECTION):
            if any(w.code in package_warnings.SIGNING_CODES for w in auth_codes):
                signed = self._signed(r, warnings)
            guides = self._auth_guides(r, signed=bool(signed))
        found = package_warnings.notices(
            warnings, section, has_auth=has_auth, signed=signed, guides=guides
        )
        return [
            {"code": n.code, "section": n.section, "text": n.text, "doc_ids": list(n.doc_ids)}
            for n in found
        ]

    def _signed(self, r: ResolvedBuild, warnings: list[PackageWarning]) -> bool:
        """The build shows request signing: a signing code beyond "no public auth", the
        producer's own words, or a signature parameter on its endpoints (Lazada, Shopee)."""
        if any(
            w.code in package_warnings.SIGNING_CODES and w.code != package_warnings.NONE_PUBLIC
            for w in warnings
        ):
            return True
        if any(w.code == package_warnings.NONE_PUBLIC and _SIGN_WORD.search(w.text)
               for w in warnings):  # fmt: skip
            return True
        if self._facts is None:
            return False
        build = r.build.build_id
        return any(
            f.location in (FieldLocation.QUERY, FieldLocation.HEADER)
            for name in SIGNATURE_PARAMS
            for f in self._facts.find(build, name, kind=FactKind.FIELD)
        )

    def _auth_guides(self, r: ResolvedBuild, *, signed: bool) -> tuple[tuple[str, str], ...]:
        """The API's guides about auth / signing (title, else a heading names it), signing
        ones first when requests are signed; at most MAX_AUTH_GUIDES."""
        scored: list[tuple[int, str, str]] = []
        for d in self._docs(r, DocumentKind.GUIDE):
            headings = [ln for ln in (d.text or "").splitlines() if ln.lstrip().startswith("#")]
            title = d.title or d.doc_id
            if _WEBHOOK_WORD.search(title):
                continue  # verifying incoming events, not signing requests
            sign = bool(_SIGN_WORD.search(title)) or any(_SIGN_WORD.search(h) for h in headings)
            auth = bool(_AUTH_WORD.search(title)) or any(_AUTH_WORD.search(h) for h in headings)
            if not (sign or auth):
                continue
            in_title = bool(_SIGN_WORD.search(title) or _AUTH_WORD.search(title))
            rank = (0 if sign and signed else 1) * 2 + (0 if in_title else 1)
            scored.append((rank, title, d.doc_id))
        scored.sort()
        return tuple((doc_id, title) for _, title, doc_id in scored[:MAX_AUTH_GUIDES])

    def webhooks(self, api: str, version: str | None = None) -> list[dict[str, Any]]:
        """connector/triggers/webhooks/*.json (the delivery mechanism), verbatim."""
        r = self._resolver.resolve(api, version)
        hooks = self._app_raw(r).get("webhooks")
        return [h for h in hooks if isinstance(h, dict)] if isinstance(hooks, list) else []

    def endpoint_refs(
        self, api: str, endpoint_ids: list[str], version: str | None = None
    ) -> dict[str, dict[str, Any] | None]:
        """The package's endpointIds (as the webhook mechanism and triggers name them) resolved
        to Plume endpoint documents: {docId, method, path}, or None when not in the build."""
        r = self._resolver.resolve(api, version)
        ids = list(dict.fromkeys(endpoint_ids))
        found = self._documents.by_source_ids(r.build.build_id, DocumentKind.ENDPOINT, ids)
        return {
            i: (
                {"doc_id": d.doc_id, "method": d.method, "path": d.path}
                if (d := found.get(i)) is not None
                else None
            )
            for i in ids
        }

    def mcp(self, api: str, version: str | None = None) -> tuple[BuildRef, dict[str, Any] | None]:
        """connector/mcp/ verbatim (None for docs-only APIs: no MCP server, by design)."""
        r = self._resolver.resolve(api, version)
        return _ref(r), _obj(self._app_raw(r).get("mcp"))

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

    def environments(self, api: str, version: str | None = None) -> tuple[BuildRef, dict[str, Any]]:
        """app.json environments + apiVersioning and the environment variables schema, verbatim
        (None when the package does not state them)."""
        r = self._resolver.resolve(api, version)
        raw = self._app_raw(r)
        app: dict[str, Any] = _obj(raw.get("app")) or {}
        envs = app.get("environments")
        return _ref(r), {
            "environments": envs if isinstance(envs, list) else None,
            "versioning": app.get("apiVersioning"),
            "base_urls": app.get("baseUrls"),
            "variables_schema": raw.get("environment_variables_schema"),
        }

    def has_icon(self, api: str, version: str | None = None) -> bool:
        r = self._resolver.resolve(api, version)
        return self._assets.has(r.build.build_id, ICON)

    def icon(self, api: str, version: str | None = None) -> tuple[BuildRef, Asset | None]:
        r = self._resolver.resolve(api, version)
        return _ref(r), self._assets.get(r.build.build_id, ICON)


def _obj(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _scopes_with_endpoints(
    scheme: dict[str, Any], endpoints: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """The scheme's scopes (verbatim), each with the endpoints whose requiredScopes name it;
    a scope only endpoints name (not in the scheme's list) is added with no description."""
    out = [
        {
            "scope": s.get("scope"),
            "description": s.get("description"),
            "endpoints": endpoints.get(str(s.get("scope")), []),
        }
        for s in scheme.get("scopes", []) or []
        if isinstance(s, dict)
    ]
    listed = {x["scope"] for x in out}
    out.extend(
        {"scope": k, "description": None, "endpoints": v}
        for k, v in endpoints.items()
        if k not in listed
    )
    return out


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
        "scopes": _scopes_with_endpoints(scheme, scope_endpoints(d)),
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
        "companions": _obj(raw.get("companions")) or {},
        "file": raw.get("file"),
    }


def _payload_view(d: Document, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """The event's payload as the loader resolved it: the schema's fields (like a model's), or
    the connector model it names, and the sample; None when the event states neither."""
    if payload is None:
        return None
    model = _obj(payload.get("model"))
    return {
        "schema_ref": payload.get("schemaRef"),
        "sample_ref": payload.get("sampleRef"),
        "model": {"doc_id": model.get("docId"), "title": model.get("title")} if model else None,
        "schema": payload.get("schema"),
        "sample": payload.get("sample"),
        "fields": [
            {
                "name": f.name,
                "location": f.location.value,
                "type": f.type,
                "required": f.required,
                "description": f.description,
                "constraints": f.constraint_dict or None,
            }
            for f in d.fields
        ],
    }


def trigger_view(d: Document) -> dict[str, Any]:
    raw = dict(d.raw or {})
    payload = _obj(raw.pop(TRIGGER_PAYLOAD_KEY, None))
    return {
        "key": d.source_id or raw.get("key"),
        "doc_id": d.doc_id,
        "title": d.title,
        "description": raw.get("description"),
        "resource": raw.get("resource"),
        "delivery": raw.get("delivery"),
        "sync_endpoint_id": raw.get("syncEndpointId"),
        "source_url": d.source_url,
        "event": raw,
        "payload": _payload_view(d, payload),
    }


def endpoint_ids_in(value: Any) -> list[str]:
    """Every ``endpointId`` / ``syncEndpointId`` string inside a JSON value, in order."""
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("endpointId", "syncEndpointId") and isinstance(v, str) and v:
                out.append(v)
            else:
                out.extend(endpoint_ids_in(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(endpoint_ids_in(v))
    return out
