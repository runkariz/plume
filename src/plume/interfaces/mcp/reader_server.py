"""Reader MCP server: read-only tools over sealed builds. The same use cases as the HTTP API."""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from plume import __version__
from plume.application.errors import ApplicationError
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.knowledge.public_changes import PublicChanges
from plume.application.models.collections import Collections
from plume.application.models.impact import ModelImpact
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import ModelSessions
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.sections import (
    PackageSections,
    endpoint_ids_in,
    scheme_view,
    trigger_view,
)
from plume.application.reader.use_cases import (
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    SearchDocs,
)
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.package_warnings import AUTH, ENVIRONMENTS
from plume.domain.shared.errors import DomainError
from plume.interfaces import payloads
from plume.interfaces.mcp.apps.model_view import (
    model_view_apps,
    model_view_html,
)
from plume.interfaces.mcp.model_tools import register_model_tools
from plume.interfaces.mcp.set_tools import register_set_tools

INSTRUCTIONS = """\
Plume serves API documentation as immutable, versioned builds. For ANY question about an API
that Plume indexes (call list_apis if unsure which), use Plume before answering and answer
ONLY from what Plume returns. Plume retrieves; you write the answer.

Rules:
1. Call search_docs(api, query) first, then get_document(api, doc_id) for the documents you
   rely on. Quote the relevant lines and cite source_url (or the doc_id).
2. Every endpoint, field, parameter, scope or limit you name must come from a Plume result in
   this conversation. Do not add general-knowledge paragraphs or asides about the API, even
   labelled ones; if Plume has nothing, say so.
3. Existence questions ("is there a field X?", "which scope?") go to find_fact(api, name). Say
   "not documented in build <id>" only when found=false AND complete=true; never "does not
   exist". With complete=false, absence is NOT proven: give the incomplete_reasons.
4. Before writing code that calls the API, check it with check_call(api, method, path, params).
5. Results carry build and docs_as_of; mention them when precision matters. version defaults
   to the "latest" tag; pass a build id to pin one.
6. Canonical models (get_model, list_models): if stale=true, the model was built on older
   builds; say so and regenerate it (or ask) before relying on it.
7. To make a model for the user: start_model_session(apis, concept) -> get_model_context ->
   get_model_evidence per API -> submit_model_draft. It is stored unlisted: give the user its
   share link. The first save returns a "My models" link (collection): give it to the user to
   bookmark, and pass the SAME collection on every later save in this conversation
   (submit_model_draft / submit_model_set) so their models stay in one list
   (list_my_models(collection)). To change a model: revise_model(id), then submit_model_draft(...,
   based_on=id) makes a new version.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


@dataclass(frozen=True, slots=True)
class McpReaderDependencies:
    overviews: Callable[[], ListApiOverviews]
    search: Callable[[], SearchDocs]
    get_document: Callable[[], GetDocument]
    find_fact: Callable[[], FindFact]
    check_call: Callable[[], CheckCall]
    list_builds: Callable[[], ListBuilds]
    diff_builds: Callable[[], DiffBuilds]
    resolver: Callable[[], BuildResolver]
    models: Callable[[], ModelSessions] | None = None
    sections: Callable[[], PackageSections] | None = None
    web_public_url: str | None = None
    suggest_related: Callable[[], SuggestRelated] | None = None
    model_sets: Callable[[], ModelSets] | None = None
    collections: Callable[[], Collections] | None = None
    public_changes: Callable[[], PublicChanges] | None = None
    model_impact: Callable[[], ModelImpact] | None = None
    mcp_app_html: str | None = None  # the model view bundle; None = the packaged file


logger = logging.getLogger(__name__)


async def _run(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return await anyio.to_thread.run_sync(fn)
    except (ApplicationError, DomainError) as exc:
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # a bug: say what kind, log the details (never the internals)
        ref = uuid.uuid4().hex[:8]
        logger.exception("MCP tool failed (ref %s)", ref)
        raise ToolError(
            f"internal error ({type(exc).__name__}); the server logged it as ref {ref}"
        ) from exc


def _forbid_unknown_arguments(server: MCPServer, name: str) -> None:
    """Make a tool refuse arguments it does not take (the MCP library ignores them, so a
    caller never learns they were dropped). No-op if the library's internals differ."""
    tool = getattr(getattr(server, "_tool_manager", None), "get_tool", lambda _n: None)(name)
    meta = getattr(tool, "fn_metadata", None)
    base = getattr(meta, "arg_model", None)
    if meta is None or not isinstance(base, type) or not issubclass(base, BaseModel):
        return
    strict = type(
        base.__name__, (base,), {"model_config": {**base.model_config, "extra": "forbid"}}
    )
    meta.arg_model = strict


def create_reader_server(deps: McpReaderDependencies) -> MCPServer:
    server = MCPServer(
        name="plume",
        title="Plume API docs",
        instructions=INSTRUCTIONS,
        version=__version__,
        extensions=[model_view_apps(deps.mcp_app_html or model_view_html())],
    )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def list_apis() -> dict[str, Any]:
        """List the APIs Plume knows, with their latest build, tags and document counts.
        notices: what to tell the user before they connect (e.g. requests must be signed;
        choose a region), each with the section it concerns."""

        def run() -> dict[str, Any]:
            apis = []
            for o in deps.overviews().execute():
                item = payloads.api_payload(o)
                if deps.sections is not None and o.ref is not None:
                    item["notices"] = deps.sections().notices(o.info.api_id.value)
                apis.append(item)
            return {"apis": apis}

        return await _run(run)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def search_docs(
        api: str,
        query: str,
        kind: Literal["all", "endpoint", "model", "guide", "auth", "app"] = "all",
        top_k: int = 8,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Search one API's documentation (hybrid semantic + full text). Use it FIRST for any
        question about an API Plume indexes; then read the hits you use with get_document and
        answer only from them."""
        return await _run(
            lambda: payloads.search_payload(
                deps.search().execute(api, query, "hybrid", kind, top_k, version)
            )
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def get_document(
        api: str, doc_id: str, version: str | None = None, full: bool = False, cursor: int = 0
    ) -> dict[str, Any]:
        """One document (endpoint, model, guide) with its source URL and anchor. Compact by
        default: plain text without the field lists (text_truncated when capped) and the fields
        as a list, 150 per page (pass next_cursor as cursor for more). full=true returns the
        whole text as stored."""

        def run() -> dict[str, Any]:
            r = deps.get_document().execute(api, doc_id, version)
            return (
                payloads.document_payload(r)
                if full
                else payloads.compact_document_payload(r, cursor)
            )

        return await _run(run)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def find_fact(
        api: str,
        name: str,
        kind: Literal["endpoint", "field", "scope"] | None = None,
        owner: str | None = None,
        resource: str | None = None,
        location: Literal["path", "query", "header", "body", "response", "model"] | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Exact lookup: is this endpoint ("GET /orders"), field ("sku", "line_items[].sku") or
        scope ("read_orders") documented? Returns evidence, or what was checked and whether the
        sources were complete (absence is only proven when complete=true)."""
        return await _run(
            lambda: payloads.find_fact_payload(
                deps.find_fact().execute(
                    api,
                    name,
                    kind=kind,
                    owner=owner,
                    resource=resource,
                    location=location,
                    version=version,
                )
            )
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def check_call(
        api: str,
        method: str,
        path: str,
        params: list[str] | None = None,
        version: str | None = None,
        query: list[str] | None = None,
        body: list[str] | None = None,
    ) -> dict[str, Any]:
        """Check a concrete call (e.g. GET /admin/api/2026-10/products/42.json with params
        ["fields"]) against the documented endpoints and their parameters. params: names in
        any request location; query / body: names (not values) checked in that location. A
        parameter named by the API's pagination contract or guide counts (where:
        "pagination"); a version segment other than the endpoint's fixed one does not. An entry
        "name=value" also gives a value: where several operations share METHOD + path and a
        fixed parameter picks one (AliExpress POST /sync with method=...), pass it; without
        it the verdict is "ambiguous" and the note says what to pass."""
        return await _run(
            lambda: payloads.check_call_payload(
                deps.check_call().execute(
                    api, method, path, params or [], version, query or [], body or []
                )
            )
        )

    _forbid_unknown_arguments(server, "check_call")  # `body` / `query` used to vanish silently

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def list_builds(api: str) -> dict[str, Any]:
        """Builds of an API (newest first) with their tags and content hashes."""

        def run() -> dict[str, Any]:
            deps.resolver().resolve(api)  # unknown api -> error
            views = deps.list_builds().execute(ApiId(api))
            return {
                "api": api,
                "builds": [
                    {
                        "build": v.build.build_id.value,
                        "status": v.build.status.value,
                        "sealed_at": v.build.sealed_at.isoformat() if v.build.sealed_at else None,
                        "items": len(v.build),
                        "tags": list(v.tags),
                    }
                    for v in views
                ],
            }

        return await _run(run)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def diff_builds(
        api: str, from_version: str, to_version: str = "latest", limit: int = 200
    ) -> dict[str, Any]:
        """Document chunks added, changed and removed between two builds (tags or build ids)."""

        def run() -> dict[str, Any]:
            resolver = deps.resolver()
            old = resolver.resolve(api, from_version).build
            new = resolver.resolve(api, to_version).build
            d = deps.diff_builds().execute(old.build_id, new.build_id)
            cap = max(1, min(limit, 1000))
            return {
                "api": api,
                "from": old.build_id.value,
                "to": new.build_id.value,
                "added": list(d.added[:cap]),
                "changed": list(d.changed[:cap]),
                "removed": list(d.removed[:cap]),
                "unchanged": d.unchanged,
                "truncated": max(len(d.added), len(d.changed), len(d.removed)) > cap,
            }

        return await _run(run)

    if deps.sections is not None:
        sections = deps.sections

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def list_auth_schemes(api: str, version: str | None = None) -> dict[str, Any]:
            """Auth schemes as the package states them (type, header/query parameter, scopes,
            variables). present=false when the package documents none. notices: tell the user
            (e.g. every request must be signed); their doc_ids are the guides that explain it."""

            def run() -> dict[str, Any]:
                ref, docs = sections().auth_schemes(api, version)
                views = [scheme_view(d) for d in docs]
                return {
                    **payloads.ref_payload(ref),
                    "present": bool(views),
                    "schemes": [
                        {
                            k: v[k]
                            for k in (
                                "id",
                                "doc_id",
                                "name",
                                "type",
                                "grant_type",
                                "header_name",
                                "header_prefix",
                                "header_source",
                                "header_evidence",
                                "header_note",
                                "query_param",
                                "scopes",
                                "variables",
                            )
                        }
                        for v in views
                    ],
                    "notices": sections().notices(api, AUTH, version),
                }

            return await _run(run)

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def get_auth_scheme(
            api: str, scheme_id: str, version: str | None = None
        ) -> dict[str, Any]:
            """One auth scheme: the package's auth JSON and variables schema verbatim.
            notices: tell the user (e.g. every request must also be signed; doc_ids: the
            guides that explain it)."""

            def run() -> dict[str, Any]:
                ref, doc = sections().auth_scheme(api, scheme_id, version)
                notices = sections().notices(api, AUTH, version)
                return {**payloads.ref_payload(ref), **scheme_view(doc), "notices": notices}

            return await _run(run)

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def get_vendor_mcp(api: str, version: str | None = None) -> dict[str, Any]:
            """The API vendor's own MCP server(s) and tools, when the package lists them
            (present=false for docs-only APIs)."""

            def run() -> dict[str, Any]:
                ref, section = sections().mcp(api, version)
                servers = section.get("servers", []) if section else []
                return {**payloads.ref_payload(ref), "present": bool(servers), "servers": servers}

            return await _run(run)

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def get_environments(api: str, version: str | None = None) -> dict[str, Any]:
            """Environments (servers, host variables) and API versioning, verbatim from the
            package (null when it does not state them)."""

            def run() -> dict[str, Any]:
                ref, env = sections().environments(api, version)
                notices = sections().notices(api, ENVIRONMENTS, version)
                return {**payloads.ref_payload(ref), **env, "notices": notices}

            return await _run(run)

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def list_triggers(api: str, version: str | None = None) -> dict[str, Any]:
            """Trigger events / webhook topics the package lists. present=false means the package
            has no triggers section (say so; do not guess topics). Webhook-management endpoints
            are endpoints tagged "webhooks" (search_docs)."""

            def run() -> dict[str, Any]:
                ref, docs = sections().triggers(api, version)
                views = [trigger_view(d) for d in docs]
                hooks = sections().webhooks(api, version)
                return {
                    **payloads.ref_payload(ref),
                    "present": bool(views or hooks),
                    "triggers": [
                        {k: v for k, v in x.items() if k not in ("event", "payload")} for x in views
                    ],
                    "webhooks": hooks,
                    "endpoint_refs": sections().endpoint_refs(
                        api,
                        endpoint_ids_in(hooks) + endpoint_ids_in([x["event"] for x in views]),
                        version,
                    ),
                }

            return await _run(run)

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def get_trigger(api: str, key: str, version: str | None = None) -> dict[str, Any]:
            """One trigger by key (e.g. "orders/create") or document id; event JSON verbatim.
            payload: the event's payload schema fields (like a model's) and sample, or the
            connector model it names (read it with get_document(model.doc_id)); null when the
            event has none."""

            def run() -> dict[str, Any]:
                ref, doc = sections().trigger(api, key, version)
                return {**payloads.ref_payload(ref), **trigger_view(doc)}

            return await _run(run)

    if deps.models is not None:
        register_model_tools(
            server,
            deps.models,
            deps.resolver,
            _run,
            False,
            deps.web_public_url,
            related=deps.suggest_related,
            collections=deps.collections,
            sets=deps.model_sets,
            impact=deps.model_impact,
        )
    if deps.model_sets is not None:
        register_set_tools(
            server, deps.model_sets, deps.resolver, _run, False, deps.web_public_url,
            impact=deps.model_impact,
        )  # fmt: skip
    if deps.public_changes is not None:
        changes = deps.public_changes

        @server.tool(annotations=READ_ONLY, structured_output=True)
        async def what_changed(api: str, since: str | None = None) -> dict[str, Any]:
            """What changed in an API's docs: the latest published build's changes, or every
            build since a date (YYYY-MM-DD) or a build id: Plume's diff between builds of the
            docs, only changes it could confirm in the vendor's docs (or that the vendor's
            changelog names, perVendorChangelog); changelog_guides are the vendor's own. Report
            ONLY these as API changes; quote the evidence; when only wording changed say "docs
            updated, no API change"."""

            def go() -> dict[str, Any]:
                out = changes().changes(api, since=since, limit=100)
                guides = deps.sections().changelog_guides(api) if deps.sections else []
                out["changelog_guides"] = guides
                out["note"] = (
                    "This is Plume's diff between builds of the vendor docs (what changed in "
                    "the docs between two loads), limited to changes Plume confirmed in the "
                    "docs (or that the vendor's changelog names). Extraction problems are never "
                    "listed here. It is not the vendor's release log"
                    + (
                        ": for the vendor's own account read "
                        + "; ".join(f"{g['title']} ({g['doc_id']})" for g in guides)
                        + "."
                        if guides
                        else "; this package has no changelog guide."
                    )
                )
                return out

            return await _run(go)

    return server
