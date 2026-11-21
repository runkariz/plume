"""One reader call as the query log keeps it, and how it is built from the call."""

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from plume.domain.querylog.redact import (
    STRICT,
    RedactionPolicy,
    call_template,
    redact_name,
    redact_text,
)

SCHEMA_VERSION = 1
MAX_TOP = 20

# The reader tools that are logged (MCP names; HTTP routes map onto them).
LOGGED_TOOLS = frozenset(
    {
        "search_docs", "find_fact", "check_call", "get_document", "list_apis", "list_builds",
        "diff_builds", "list_auth_schemes", "get_auth_scheme", "get_environments",
        "list_triggers", "get_trigger", "what_changed", "get_vendor_mcp", "get_model_context",
        "get_model_evidence", "browse_docs", "get_api", "ask",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class QueryEvent:
    occurred_at: datetime
    surface: str  # mcp | http
    tool: str
    api: str | None = None
    apis: tuple[str, ...] = ()  # a model session's APIs (names only)
    build_id: str | None = None
    version_requested: str | None = None
    query_text: str | None = None  # search query / model concept, redacted
    call_method: str | None = None
    call_path_template: str | None = None
    param_names: tuple[str, ...] = ()
    fact_kind: str | None = None
    fact_name: str | None = None
    doc_id: str | None = None
    top_docs: tuple[tuple[str, int], ...] = ()  # (doc id, rank)
    result_count: int | None = None
    verdict: str | None = None
    complete: bool | None = None
    answered_by: str | None = None  # check_call: the matched doc id
    error_class: str | None = None
    latency_ms: int | None = None
    client_name: str | None = None
    session_hash: str | None = None
    redactions: int = 0
    schema_version: int = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "occurred_at": self.occurred_at.isoformat(), "surface": self.surface,
            "tool": self.tool, "api": self.api, "apis": list(self.apis),
            "build_id": self.build_id, "version_requested": self.version_requested,
            "query_text": self.query_text, "call_method": self.call_method,
            "call_path_template": self.call_path_template, "param_names": list(self.param_names),
            "fact_kind": self.fact_kind, "fact_name": self.fact_name, "doc_id": self.doc_id,
            "top_docs": [{"doc_id": d, "rank": r} for d, r in self.top_docs],
            "result_count": self.result_count, "verdict": self.verdict,
            "complete": self.complete, "answered_by": self.answered_by,
            "error_class": self.error_class, "latency_ms": self.latency_ms,
            "client_name": self.client_name, "session_hash": self.session_hash,
            "redactions": self.redactions, "schema_version": self.schema_version,
        }  # fmt: skip


def session_hash(session_id: str | None, salt: bytes) -> str | None:
    """A session id as a keyed hash: groups one conversation, identifies no one."""
    if not session_id:
        return None
    return hmac.new(salt, session_id.encode(), hashlib.sha256).hexdigest()[:16]


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _doc_ids(payload: Mapping[str, Any]) -> list[str]:
    hits: Any = payload.get("hits")
    if not isinstance(hits, list):
        hits = payload.get("items")
    out: list[str] = []
    for h in hits if isinstance(hits, list) else []:
        if isinstance(h, Mapping):
            i = h.get("doc_id") or h.get("id")
            if isinstance(i, str):
                out.append(i)
    return out


def build_event(
    tool: str,
    surface: str,
    args: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
    *,
    at: datetime,
    latency_ms: int | None,
    error_class: str | None = None,
    client_name: str | None = None,
    session_id: str | None = None,
    salt: bytes = b"",
    policy: RedactionPolicy = STRICT,
) -> QueryEvent:
    """The logged form of one reader call. Only names, ids, our doc ids and redacted text are
    kept: never parameter values, bodies, headers or auth."""
    p: Mapping[str, Any] = payload or {}
    red = 0
    api = _str(args.get("api")) or _str(p.get("api"))
    fields: dict[str, Any] = {}
    if tool in ("search_docs", "ask"):
        fields["query_text"], red = redact_text(_str(args.get("query") or args.get("question")))
        ids = _doc_ids(p)
        fields["top_docs"] = tuple((d, i) for i, d in enumerate(ids[:MAX_TOP], 1))
        fields["result_count"] = len(ids)
    elif tool == "check_call":
        entries = [str(e) for key in ("params", "query", "body")
                   for e in (args.get(key) or []) if isinstance(e, str)]  # fmt: skip
        template, names, red = call_template(str(args.get("path") or ""), entries, policy)
        matched = p.get("matched") if isinstance(p.get("matched"), Mapping) else None
        fields.update(
            call_method=(_str(args.get("method")) or "").upper()[:10] or None,
            call_path_template=template,
            param_names=tuple(names),
            verdict=_str(p.get("verdict")),
            complete=p.get("complete") if isinstance(p.get("complete"), bool) else None,
            answered_by=_str(matched.get("doc_id")) if matched else None,
        )
    elif tool == "find_fact":
        name, red = redact_name(_str(args.get("name")))
        found = p.get("found")
        fields.update(
            fact_kind=_str(args.get("kind")),
            fact_name=name,
            verdict=("found" if found else "not_found") if isinstance(found, bool) else None,
            complete=p.get("complete") if isinstance(p.get("complete"), bool) else None,
        )
    elif tool in ("get_document", "get_auth_scheme", "get_trigger"):
        fields["doc_id"] = _str(args.get("doc_id") or args.get("scheme_id")
                                or args.get("trigger_id"))  # fmt: skip
    elif tool == "browse_docs":
        ids = _doc_ids(p)
        fields["top_docs"] = tuple((d, i) for i, d in enumerate(ids[:MAX_TOP], 1))
        fields["result_count"] = len(ids)
    elif tool in ("get_model_context", "get_model_evidence"):
        concept, red = redact_name(_str(p.get("concept")))
        listed: Any = p.get("apis")
        api_names: list[str] = []
        for a in listed if isinstance(listed, list) else []:
            n = a.get("api") if isinstance(a, Mapping) else a
            if isinstance(n, str):
                api_names.append(n)
        fields.update(query_text=concept, apis=tuple(api_names))
    client, red_client = redact_name(client_name)
    return QueryEvent(
        occurred_at=at,
        surface=surface,
        tool=tool,
        api=api,
        build_id=_str(p.get("build")),
        version_requested=_str(args.get("version")) or _str(args.get("to_version")),
        latency_ms=latency_ms,
        error_class=error_class,
        client_name=client,
        session_hash=session_hash(session_id, salt),
        redactions=red + red_client,
        **fields,
    )
