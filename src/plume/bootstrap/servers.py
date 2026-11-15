"""Builds the HTTP and MCP ASGI apps from a container, and serves them."""

import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from plume.bootstrap.container import Container
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server


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
            mcp_url=s.mcp_public_url,
            rate_limit_per_minute=s.reader_rate_limit_per_minute,
            cors_origins=s.cors_origins,
            maintainer=c.maintainer,
            maintainer_tokens=tuple(t.get_secret_value() for t in s.maintainer_tokens),
            max_upload_bytes=s.max_upload_bytes,
        )
    )


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
        )
    )


def mcp_app(c: Container) -> Starlette:
    hosts = list(c.settings.mcp_allowed_hosts)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"http://{h}" for h in hosts] + [f"https://{h}" for h in hosts],
    )
    return reader_server(c).streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        host=c.settings.mcp_host,
        transport_security=security,
    )


def serve_api(c: Container, host: str | None = None, port: int | None = None) -> None:
    s = c.settings
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
