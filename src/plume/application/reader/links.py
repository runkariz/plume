"""Cross links a package states, read from a document's raw JSON (set at load time by the
package reader): an endpoint's required scopes per auth scheme and its knowledge units, a
unit's endpoints, an auth scheme's endpoints per scope. Missing links read as empty."""

from typing import Any

from plume.domain.knowledge.document import Document, DocumentKind


def _raw(doc: Document) -> dict[str, Any]:
    return doc.raw if isinstance(doc.raw, dict) else {}


def _ids(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def required_scopes(doc: Document) -> list[dict[str, Any]]:
    """An endpoint's ``requiredScopes``: [{authId, scopes}] (authId None when not stated)."""
    if doc.kind is not DocumentKind.ENDPOINT:
        return []
    out = []
    for entry in _raw(doc).get("requiredScopes") or []:
        if isinstance(entry, dict) and _ids(entry.get("scopes")):
            auth = entry.get("authId")
            out.append(
                {
                    "authId": auth if isinstance(auth, str) else None,
                    "scopes": _ids(entry["scopes"]),
                }
            )
    return out


def linked_endpoints(doc: Document) -> list[str]:
    """A knowledge unit's endpoints (Core's endpointId/endpointIds) as document ids."""
    if doc.kind is not DocumentKind.GUIDE or doc.doc_id.startswith("guide:page-"):
        return []
    return _ids(_raw(doc).get("endpoints"))


def endpoint_links(doc: Document) -> list[dict[str, str]]:
    """A knowledge unit's endpoints with why they are linked: [{endpointId, linkBasis}], where
    linkBasis is "text" (the unit names it), "page" or "slug" (knowledge-export/unit-links.json)."""
    if not linked_endpoints(doc):
        return []
    value = _raw(doc).get("endpointLinks")
    if not isinstance(value, list):  # loaded before link bases existed
        return [{"endpointId": e, "linkBasis": "text"} for e in linked_endpoints(doc)]
    return [
        {"endpointId": e["endpoint"], "linkBasis": str(e.get("linkBasis") or "text")}
        for e in value
        if isinstance(e, dict) and isinstance(e.get("endpoint"), str)
    ]


def linked_guides(doc: Document) -> list[str]:
    """The knowledge units that name this endpoint."""
    if doc.kind is not DocumentKind.ENDPOINT:
        return []
    return _ids(_raw(doc).get("x-plume-guides"))


def scope_endpoints(doc: Document) -> dict[str, list[str]]:
    """An auth scheme's scopes -> the endpoints that require them."""
    if doc.kind is not DocumentKind.AUTH:
        return {}
    value = _raw(doc).get("scopeEndpoints")
    if not isinstance(value, dict):
        return {}
    return {k: _ids(v) for k, v in value.items() if isinstance(k, str)}
