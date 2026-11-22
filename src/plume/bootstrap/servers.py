"""Builds the HTTP and MCP ASGI apps from a container, and serves them."""

import contextlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from plume.bootstrap.container import Container
from plume.bootstrap.mcp_debug import McpDebugLog
from plume.bootstrap.mcp_debug import enable as enable_mcp_debug
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.http.rate_limit import RateLimitMiddleware
from plume.interfaces.mcp.maintainer_server import (
    McpMaintainerDependencies,
    create_maintainer_server,
)
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server

logger = logging.getLogger("plume.server")


def http_app(c: Container) -> FastAPI:
    s = c.settings
    return create_app(
        HttpDependencies(
            overviews=c.overviews,
            browse=c.browse,
            search=c.search,
            get_document=c.get_document,
            find_fact=c.find_fact,
            check_call=c.check_call,
            list_builds=c.list_builds,
            diff_builds=c.diff_builds,
            resolver=c.resolver,
            sections=c.sections,
            mcp_url=s.mcp_public_url,
            rate_limit_per_minute=s.reader_rate_limit_per_minute,
            trusted_proxy_hops=s.trusted_proxy_hops,
            cors_origins=s.cors_origins,
            maintainer=c.maintainer,
            suggest=c.suggest,
            models=c.models,
            maintainer_tokens=tuple(t.get_secret_value() for t in s.maintainer_tokens),
            max_upload_bytes=s.max_upload_bytes,
            generate_models=c.generate,
            suggest_related=c.suggest_related,
            model_sets=c.model_sets,
            web_public_url=s.web_public_url,
            collections=c.collections,
            release_notes=c.release_notes,
            api_display=c.api_display,
            remove_api=c.remove_api,
            public_changes=c.public_changes,
            model_impact=c.model_impact,
            model_evaluation=c.model_evaluation,
            reports=lambda: c.reported_questions,
            mapping_reports=lambda: c.mapping_reports,
        )
    )


def _app_html(c: Container) -> str | None:
    path = c.settings.mcp_app_html
    return path.read_text(encoding="utf-8") if path is not None else None


def reader_server(c: Container) -> MCPServer:
    return create_reader_server(
        McpReaderDependencies(
            overviews=c.overviews,
            search=c.search,
            get_document=c.get_document,
            find_fact=c.find_fact,
            check_call=c.check_call,
            list_builds=c.list_builds,
            diff_builds=c.diff_builds,
            resolver=c.resolver,
            models=c.models,
            sections=c.sections,
            suggest_related=c.suggest_related,
            model_sets=c.model_sets,
            collections=c.collections,
            public_changes=c.public_changes,
            model_impact=c.model_impact,
            web_public_url=c.settings.web_public_url,
            mcp_app_html=_app_html(c),
            reports=(lambda: c.reported_questions) if c.settings.reports else None,
            mapping_reports=(lambda: c.mapping_reports) if c.settings.reports else None,
            trusted_proxy_hops=c.settings.trusted_proxy_hops,
        )
    )


def maintainer_mcp_server(c: Container) -> MCPServer:
    return create_maintainer_server(
        McpMaintainerDependencies(
            suggest=c.suggest,
            models=c.models,
            resolver=c.resolver,
            tag_build=c.tag_build,
            jobs=c.maintainer,
            generate=c.generate,
            suggest_related=c.suggest_related,
            model_sets=c.model_sets,
            web_public_url=c.settings.web_public_url,
            mcp_app_html=_app_html(c),
            release_notes=c.release_notes,
            api_display=c.api_display,
            remove_api=c.remove_api,
        )
    )


class BearerGate:
    """ASGI wrapper: the maintainer MCP endpoint needs a maintainer bearer token."""

    def __init__(self, app: ASGIApp, tokens: tuple[str, ...]) -> None:
        self._app = app
        self._tokens = tokens

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            scheme, _, token = headers.get(b"authorization", b"").decode().partition(" ")
            ok = scheme.lower() == "bearer" and any(
                hmac.compare_digest(token.encode(), t.encode()) for t in self._tokens
            )
            if not ok:
                status = 503 if not self._tokens else 401
                response = JSONResponse(
                    {"error": "unauthorized", "message": "maintainer bearer token required"},
                    status_code=status,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def mcp_app(c: Container) -> Starlette:
    hosts = list(c.settings.mcp_allowed_hosts)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"http://{h}" for h in hosts] + [f"https://{h}" for h in hosts],
    )
    reader = reader_server(c)
    maintainer = maintainer_mcp_server(c)
    reader_app = reader.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        host=c.settings.mcp_host,
        transport_security=security,
    )
    maintainer_app = maintainer.streamable_http_app(
        streamable_http_path="/maintainer/mcp",
        stateless_http=True,
        host=c.settings.mcp_host,
        transport_security=security,
    )
    tokens = tuple(t.get_secret_value() for t in c.settings.maintainer_tokens)

    async def health(_: Request) -> JSONResponse:
        """For k8s probes: no auth, not rate limited, no database call."""
        return JSONResponse({"status": "ok"})

    routes = [Route("/health", health, methods=["GET"]), *reader_app.routes]
    for route in maintainer_app.routes:
        if isinstance(route, Route) and route.path == "/maintainer/mcp":
            routes.append(Route(route.path, endpoint=BearerGate(route.app, tokens)))

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with reader.session_manager.run(), maintainer.session_manager.run():
            yield

    # The public reader MCP is rate limited per client address like the HTTP reader API.
    limit = c.settings.reader_rate_limit_per_minute
    middleware = [
        Middleware(
            RateLimitMiddleware,
            per_minute=limit,
            trusted_tokens=tokens,
            trusted_proxy_hops=c.settings.trusted_proxy_hops,
        )
    ]
    if c.settings.mcp_cors_origins:  # outermost, so preflights and 429s carry CORS headers
        middleware.insert(
            0,
            Middleware(
                CORSMiddleware,
                allow_origins=list(c.settings.mcp_cors_origins),
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=[
                    "Authorization",
                    "Content-Type",
                    "Accept",
                    "Last-Event-ID",
                    "Mcp-Session-Id",
                    "Mcp-Protocol-Version",
                ],
                expose_headers=["Mcp-Session-Id", "Retry-After"],
            ),
        )
    if c.settings.mcp_debug:
        enable_mcp_debug()
        middleware.append(Middleware(McpDebugLog))
    return Starlette(routes=routes, lifespan=lifespan, middleware=middleware)


def recover_jobs(c: Container) -> None:
    try:
        ids = c.maintainer().recover()
    except Exception:
        logger.exception("job recovery skipped")
        return
    if ids:
        logger.warning("marked %d interrupted job(s) as failed: %s", len(ids), ", ".join(ids))
    try:
        model_ids = c.generate().recover()
    except Exception:
        logger.exception("model job recovery skipped")
        return
    if model_ids:
        logger.warning("marked %d interrupted model job(s) as failed", len(model_ids))


def serve_api(c: Container, host: str | None = None, port: int | None = None) -> None:
    s = c.settings
    recover_jobs(c)
    uvicorn.run(http_app(c), host=host or s.api_host, port=port or s.api_port, log_level="info")


def serve_mcp(c: Container, host: str | None = None, port: int | None = None) -> None:
    s = c.settings
    uvicorn.run(mcp_app(c), host=host or s.mcp_host, port=port or s.mcp_port, log_level="info")


def openapi_document(c: Container | None = None) -> str:
    """The OpenAPI document (no database needed to build it)."""
    app = http_app(c or Container())
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def write_openapi(path: Path) -> None:
    path.write_text(openapi_document(), encoding="utf-8")
