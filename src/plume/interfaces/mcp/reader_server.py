"""Reader MCP server: read-only tools over sealed builds. The same use cases as the HTTP API."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from plume import __version__
from plume.application.errors import ApplicationError
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.use_cases import (
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    SearchDocs,
)
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.errors import DomainError
from plume.interfaces import payloads

INSTRUCTIONS = """\
Plume serves API documentation as immutable, versioned builds. Use it to answer technical
questions about an API with citations. Plume retrieves; you write the answer.

How to answer:
1. list_apis to see what is available (ids like "shopify").
2. search_docs(api, query) to find endpoints, models and guides; then get_document(api, doc_id)
   to read the ones you will rely on. Quote and cite source_url.
3. For "does X exist / is field Y documented / which scope" use find_fact(api, name). It checks
   an exact index of endpoints, fields and scopes. Only say something is "not documented" when
   find_fact returns found=false AND complete=true, and say "not documented in build <id>",
   never "does not exist". If complete=false, absence is NOT proven: say so.
4. To validate a call you plan to make, use check_call(api, method, path, params).
5. Every result carries build and docs_as_of; mention them when precision matters.
   version defaults to the "latest" tag; pass a build id to pin one.
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


async def _run(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return await anyio.to_thread.run_sync(fn)
    except (ApplicationError, DomainError) as exc:
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


def create_reader_server(deps: McpReaderDependencies) -> MCPServer:
    server = MCPServer(
        name="plume",
        title="Plume API docs",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def list_apis() -> dict[str, Any]:
        """List the APIs Plume knows, with their latest build, tags and document counts."""
        return await _run(
            lambda: {"apis": [payloads.api_payload(o) for o in deps.overviews().execute()]}
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def search_docs(
        api: str,
        query: str,
        kind: Literal["all", "endpoint", "model", "guide", "auth", "app"] = "all",
        top_k: int = 8,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Hybrid (semantic + full-text) search of one API's docs. Returns ranked documents
        with snippets; read the ones you use with get_document."""
        return await _run(
            lambda: payloads.search_payload(
                deps.search().execute(api, query, "hybrid", kind, top_k, version)
            )
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def get_document(api: str, doc_id: str, version: str | None = None) -> dict[str, Any]:
        """Full text of one document (endpoint, model, guide) with its source URL and anchor."""
        return await _run(
            lambda: payloads.document_payload(deps.get_document().execute(api, doc_id, version))
        )

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
    ) -> dict[str, Any]:
        """Check a concrete call (e.g. GET /admin/api/2026-10/products/42.json with params
        ["fields"]) against the documented endpoints and their parameters."""
        return await _run(
            lambda: payloads.check_call_payload(
                deps.check_call().execute(api, method, path, params or [], version)
            )
        )

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

    return server
