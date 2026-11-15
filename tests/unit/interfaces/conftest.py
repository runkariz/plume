from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "shopify-mini"))
    s.load(str(packages / "test-catalog"))
    return s


def http_deps(stack: FakeStack, rate: int = 0) -> HttpDependencies:
    return HttpDependencies(
        overviews=stack.overviews,
        browse=stack.browse,
        search=stack.search,
        get_document=stack.get_document,
        find_fact=stack.find_fact,
        check_call=stack.check_call,
        list_builds=lambda: ListBuilds(stack.builds, stack.tags),
        diff_builds=lambda: DiffBuilds(stack.builds),
        resolver=stack.resolver,
        rate_limit_per_minute=rate,
    )


@pytest.fixture
def app(stack: FakeStack) -> FastAPI:
    return create_app(http_deps(stack))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def mcp_server(stack: FakeStack) -> MCPServer:
    return create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews,
            search=stack.search,
            get_document=stack.get_document,
            find_fact=stack.find_fact,
            check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds),
            resolver=stack.resolver,
        )
    )
