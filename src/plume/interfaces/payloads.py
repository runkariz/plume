"""Plain-JSON payloads of reader results. MCP tools return exactly these; the HTTP API shows
the same JSON as ``claudePayload`` so the web can display what Claude receives."""

from typing import Any

from plume.application.models.concepts import Suggestions
from plume.application.models.sessions import revise_prompt
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
from plume.domain.models.canonical_model import CanonicalField
from plume.domain.models.snapshot import ModelSnapshot, Visibility
from plume.domain.models.validation import Issue

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
        "quality": ({**o.eval.metrics.as_dict(), "gate_passed": o.eval.passed} if o.eval else None),
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
        "incomplete_reasons": list(r.reasons),
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


# -- canonical models ----------------------------------------------------------------------------


def _short(name: str) -> str:
    """First word of the display name, its casing kept ("WooCommerce", "Shopify Admin" ->
    "Shopify"); only an all-lowercase word is capitalised."""
    if not name:
        return name
    word = name.split(maxsplit=1)[0]
    return word if word != word.lower() else word[:1].upper() + word[1:]


def api_ref(api: str, name: str) -> Json:
    """ApiRef without the logo (HTTP adds it)."""
    return {"id": api, "name": name, "shortName": _short(name)}


def suggestions_payload(s: Suggestions) -> Json:
    return {
        "apis": [
            api_ref(r.api.api_id.value, r.api.name) | {"build": r.build.build_id.value}
            for r in s.apis
        ],
        "concepts": [
            {
                "id": c.key,
                "name": c.name,
                "reason": c.reason,
                "apiCounts": {
                    a: {
                        "models": n.models,
                        "endpoints": n.endpoints,
                        "operations": list(n.operations),
                        "fields": n.fields,
                    }
                    for a, n in c.api_counts.items()
                },
                "likelyFields": c.likely_fields,
                "coverage": c.coverage,
                "operations": list(c.operations),
                "difficulty": {"tone": c.difficulty[0], "label": c.difficulty[1]},
                "documents": {a: list(ids) for a, ids in c.doc_ids.items()},
            }
            for c in s.concepts
        ],
        "total": s.total,
        "limit": s.limit,
        "offset": s.offset,
        "nextOffset": s.next_offset,
        "counts": {
            "all": s.counts.all,
            "inAll": s.counts.in_all,
            "write": s.counts.write,
            "single": s.counts.single,
        },
        "notModeled": {
            "count": s.not_modeled,
            "summary": ", ".join(s.not_modeled_examples) or "none",
        },
    }


def snapshot_payload(
    m: ModelSnapshot, names: dict[str, str], stale_inputs: list[dict[str, str | None]] | None = None
) -> Json:
    """The ModelSnapshot JSON (HTTP and MCP). ``stale`` = a pinned build is no longer latest."""
    supports = {i.api: m.support(i.api) for i in m.inputs}

    def field(f: CanonicalField, path: str) -> Json:
        sources = {}
        for api, src in f.sources:
            sources[api] = {
                "paths": [{"path": p.path, "type": p.type or ""} for p in src.paths],
                "transform": src.transform,
                "fetch": {"endpoint": src.fetch} if src.fetch else None,
                "join": list(src.join),
                "evidence": [
                    {"quote": e.quote, "anchor": e.anchor or "", "docId": e.doc_id}
                    for e in src.evidence
                ],
            }
        out: Json = {
            "name": f.name,
            "path": path,
            "type": f.type,
            "description": f.description,
            "required": f.required,
            "support": {api: s[path] for api, s in supports.items()},
            "sources": sources,
        }
        if f.fields:
            out["fields"] = [field(c, f"{f.child_path(path)}.{c.name}") for c in f.fields]
        return out

    fields = [field(f, f.name) for f in m.draft.fields]
    coverage = {api: {"mapped": n, "total": t} for api, (n, t) in m.coverage().items()}
    return {
        "id": m.snapshot_id,
        "name": m.draft.name,
        "description": m.draft.description,
        "concept": m.concept,
        "status": m.status,
        "stale": bool(stale_inputs),
        "staleInputs": list(stale_inputs or []),
        "generatedAt": m.created_at.isoformat(),
        "promptVersion": m.prompt_version,
        "sessionId": m.session_id,
        "inputs": [api_ref(i.api, names.get(i.api, i.api)) | {"build": i.build} for i in m.inputs],
        "fields": fields,
        "openQuestions": [
            {"question": q.question, "detail": q.detail, "options": list(q.options)}
            for q in m.draft.open_questions
        ],
        "coverage": coverage,
        "citations": {
            "checked": m.citations_checked,
            "found": m.citations_checked,
            "missing": [],
        },
    }


def model_list_item(
    m: ModelSnapshot,
    stale_inputs: list[dict[str, str | None]],
    versions: int | None = None,
) -> Json:
    return {
        "snapshot_id": m.snapshot_id,
        "name": m.draft.name,
        "concept": m.concept,
        "apis": [i.api for i in m.inputs],
        "created_at": m.created_at.isoformat(),
        "stale": bool(stale_inputs),
        "stale_inputs": stale_inputs,
        "visibility": m.visibility,
        "official": m.visibility == Visibility.OFFICIAL,
        "version": m.version,
        "versions": versions if versions is not None else m.version,
        "lineage_id": m.lineage,
    }


def share_path(snapshot_id: str) -> str:
    return f"/models/{snapshot_id}"


def access_payload(m: ModelSnapshot, lineage: Json, web_url: str | None) -> Json:
    """Who can see the model, where it came from, its versions and its link (camelCase)."""
    path = share_path(m.snapshot_id)
    return {
        "visibility": m.visibility,
        "official": m.visibility == Visibility.OFFICIAL,
        "origin": m.origin,
        "generator": m.generator,
        "releasedAt": m.released_at.isoformat() if m.released_at else None,
        "basedOn": m.based_on,
        "lineage": {
            "id": lineage["id"],
            "version": lineage["version"],
            "versions": lineage["versions"],
            "basedOn": lineage["based_on"],
            "latestId": lineage["latest_id"],
            "history": [
                {
                    "id": h["id"],
                    "version": h["version"],
                    "createdAt": h["created_at"],
                    "visibility": h["visibility"],
                }
                for h in lineage["history"]
            ],
        },
        "sharePath": path,
        "shareUrl": web_url.rstrip("/") + path if web_url else None,
        "revisePrompt": revise_prompt(m.snapshot_id),
    }


STALE_HINT = (
    "A model with stale=true was built on older builds of at least one API (see stale_inputs): "
    "say so, and regenerate it (start_model_session) or ask before relying on it."
)


def refusal_payload(issues: list[Issue]) -> Json:
    return {
        "accepted": False,
        "issues": [
            {"code": i.code, "field": i.field, "api": i.api, "message": i.message} for i in issues
        ],
        "next": "Fix the listed mappings (or drop them) and call submit_model_draft again.",
    }
