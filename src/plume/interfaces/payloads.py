"""Plain-JSON payloads of reader results. MCP tools return exactly these; the HTTP API shows
the same JSON as ``claudePayload`` so the web can display what Claude receives."""

from typing import Any

from plume.application.reader.dto import (
    ApiOverview,
    BuildRef,
    CheckCallResult,
    DocumentResult,
    FindFactResult,
    SearchHit,
    SearchResult,
)
from plume.domain.knowledge.citation import Citation

Json = dict[str, Any]


def ref_payload(ref: BuildRef) -> Json:
    return {"api": ref.api, "build": ref.build, "tag": ref.tag, "docs_as_of": ref.docs_as_of}


def citation_payload(c: Citation) -> Json:
    return {"doc_id": c.doc_id, "source_url": c.source_url, "anchor": c.anchor, "quote": c.quote}


def api_payload(o: ApiOverview) -> Json:
    return {
        "api": o.info.api_id.value,
        "name": o.info.name,
        "summary": o.info.summary,
        "category": o.info.category.key if o.info.category else None,
        "doc_link": o.info.doc_link,
        "versions": list(o.info.versions),
        "tags": list(o.tags),
        "latest": ref_payload(o.ref) if o.ref else None,
        "counts": o.counts,
    }


def hit_payload(h: SearchHit) -> Json:
    return {
        "doc_id": h.doc_id,
        "kind": h.kind.value,
        "title": h.title,
        "subtitle": h.subtitle,
        "snippet": h.snippet,
        "source_url": h.source_url,
        "score": h.fused,
    }


def search_payload(r: SearchResult) -> Json:
    return {
        **ref_payload(r.ref),
        "query": r.query,
        "mode": r.mode,
        "results": [hit_payload(h) for h in r.hits],
        "next": "Call get_document(doc_id) to read a result in full before answering; cite "
        "source_url.",
    }


def document_payload(r: DocumentResult) -> Json:
    d = r.document
    return {
        **ref_payload(r.ref),
        "doc_id": d.doc_id,
        "kind": d.kind.value,
        "title": d.title,
        "resource": d.resource,
        "method": d.method,
        "path": d.path,
        "deprecated": d.deprecated,
        "complete": d.complete,
        "source_url": d.source_url,
        "anchor": d.anchor,
        "text": d.text,
        "citation": citation_payload(r.citation),
    }


def find_fact_payload(r: FindFactResult) -> Json:
    return {
        **ref_payload(r.ref),
        "name": r.name,
        "found": r.found,
        "complete": r.complete,
        "checked": r.checked,
        "matches": [
            {
                "kind": m.kind.value,
                "name": m.name,
                "owner_id": m.owner_id,
                "owner_title": m.owner_title,
                "resource": m.resource,
                "location": m.location.value if m.location else None,
                "type": m.type,
                "required": m.required,
                "complete": m.complete,
                "evidence": citation_payload(m.citation),
            }
            for m in r.matches
        ],
        "incomplete_sources": list(r.incomplete_sources),
        "text_mentions": [hit_payload(h) for h in r.text_mentions],
        "wording": r.wording,
    }


def check_call_payload(r: CheckCallResult) -> Json:
    return {
        **ref_payload(r.ref),
        "call": f"{r.method} {r.path}",
        "verdict": r.verdict,
        "complete": r.complete,
        "matched": (
            {"doc_id": r.matched_id, "method": r.matched_method, "path": r.matched_path}
            if r.matched_id
            else None
        ),
        "params": [{"name": p.name, "found": p.found, "where": p.where} for p in r.params],
        "checked": r.checked,
        "evidence": citation_payload(r.citation) if r.citation else None,
    }
