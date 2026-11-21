# ruff: noqa: E501
"""Reported questions over the real streamable-HTTP transport (stateless, as served): the
client name comes from the request metadata and the hourly limit counts per connection when
there is no session id. Plus the session-id header path."""

import contextlib
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
from mcp import Client
from mcp.types import Implementation
from starlette.applications import Starlette
from starlette.requests import Request

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reports.service import ReportedQuestions
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from plume.interfaces.mcp.report_tools import client_of
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.reports import InMemoryReports
from tests.fakes.stack import FakeStack

API = "test-catalog-api"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def served(packages: Path) -> Iterator[tuple[str, InMemoryReports]]:
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(packages / "test-catalog"))
    repo = InMemoryReports()
    svc = ReportedQuestions(repo, stack.embedder, stack.resolver(), FakeClock(), enabled=True,
                            salt=b"k", per_hour=2)  # fmt: skip
    server = create_reader_server(McpReaderDependencies(
        overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
        find_fact=stack.find_fact, check_call=stack.check_call,
        list_builds=lambda: ListBuilds(stack.builds, stack.tags),
        diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
        reports=lambda: svc,
    ))  # fmt: skip
    inner = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                       host="127.0.0.1")  # fmt: skip

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with server.session_manager.run():
            yield

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(Starlette(routes=list(inner.routes), lifespan=lifespan),
                                        host="127.0.0.1", port=port, log_level="warning"))  # fmt: skip
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp", repo
    srv.should_exit = True
    thread.join(timeout=10)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_client_name_and_the_hourly_limit_over_the_real_transport(
    served: tuple[str, InMemoryReports], mode: str
) -> None:
    """auto: protocol 2026-07-28 (clientInfo in every request's metadata); legacy: the
    initialize handshake, which a stateless server does not keep for later calls."""
    url, repo = served
    info = Implementation(name="coord-probe", version="1")
    async with Client(url, client_info=info, mode=mode) as client:
        one = await client.call_tool("report_question",
                                     {"api": API, "question": "how are list results paged"})  # fmt: skip
        assert not one.is_error, one.content
        two = await client.call_tool("add_to_report",
                                     {"id": one.structured_content["id"], "note": "also needed"})  # fmt: skip
        assert not two.is_error, two.content
        three = await client.call_tool("report_question",
                                       {"api": API, "question": "what is the rate limit"})  # fmt: skip
        assert three.is_error
        assert "in the last hour" in str(three.content)
    [report] = repo.reports.values()
    # legacy on a stateless server: the tool call carries no clientInfo, only a User-Agent
    expected = "coord-probe" if mode == "auto" else "python-httpx"
    assert (report.client_name or "").startswith(expected)
    assert (repo.all_notes[0].client_name or "").startswith(expected)


def test_a_session_id_header_is_the_session(packages: Path) -> None:
    scope: dict[str, Any] = {
        "type": "http", "method": "POST", "path": "/mcp", "client": ("10.0.0.5", 1234),
        "headers": [(b"mcp-session-id", b"sess-42"), (b"user-agent", b"x")],
    }  # fmt: skip
    rc = SimpleNamespace(meta={"io.modelcontextprotocol/clientInfo": {"name": "claude-code"}},
                         session=SimpleNamespace(client_params=None), request=Request(scope))  # fmt: skip
    who = client_of(SimpleNamespace(request_context=rc))  # type: ignore[arg-type]
    assert (who.client_name, who.session_id, who.address) == ("claude-code", "sess-42", "10.0.0.5")
    old = SimpleNamespace(
        meta=None, request=None,
        session=SimpleNamespace(client_params=SimpleNamespace(client_info=SimpleNamespace(name="old-client"))),
    )  # fmt: skip
    assert client_of(SimpleNamespace(request_context=old)).client_name == "old-client"  # type: ignore[arg-type]
    assert client_of(None).client_name is None
