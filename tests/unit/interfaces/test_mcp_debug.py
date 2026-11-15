"""The opt-in MCP debug log: methods and the Apps negotiation, never arguments or tokens."""

import logging

import pytest
from fastapi.testclient import TestClient

from plume.bootstrap.container import Container
from plume.bootstrap.mcp_debug import describe
from plume.bootstrap.servers import mcp_app
from plume.infrastructure.settings import Settings

UI = {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}


def test_describe_logs_safe_fields_only() -> None:
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {"extensions": UI},
                   "clientInfo": {"name": "claude-ai", "version": "0.1.0"}},
    }  # fmt: skip
    assert describe(init) == (
        "initialize client='claude-ai' version='0.1.0' protocol='2025-06-18' ui_extension=True"
    )
    plain = {"method": "initialize", "params": {"capabilities": {}}}
    assert describe(plain).endswith("ui_extension=False")
    call = {"method": "tools/call", "params": {"name": "get_model",
            "arguments": {"snapshot_id": "u-secret"}}}  # fmt: skip
    assert describe(call) == "tools/call get_model"
    assert "u-secret" not in describe(call)
    per_request = {"method": "tools/list", "params": {"_meta": {
        "io.modelcontextprotocol/clientCapabilities": {"extensions": UI}}}}  # fmt: skip
    assert describe(per_request) == "tools/list ui-in-_meta"
    assert describe({"method": "resources/read", "params": {"uri": "ui://plume/model-view"}}) == (
        "resources/read ui://plume/model-view"
    )
    assert describe({"method": "resources/read", "params": {"uri": "file:///etc"}}) == (
        "resources/read (non-ui resource)"
    )
    assert describe({"id": 1, "result": {}}) == "response"


def test_debug_log_is_opt_in_and_requests_still_work(caplog: pytest.LogCaptureFixture) -> None:
    headers = {"Accept": "application/json, text/event-stream"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    for debug, expected in ((False, []), (True, ["mcp /mcp ping"])):
        caplog.clear()
        settings = Settings(embedder="hash", mcp_debug=debug, reader_rate_limit_per_minute=0)
        with (
            caplog.at_level(logging.INFO, logger="plume.mcp.debug"),
            TestClient(
                mcp_app(Container(settings=settings)), base_url="http://127.0.0.1:18481"
            ) as client,
        ):
            r = client.post("/mcp", json=body, headers=headers)
        assert r.status_code == 200
        assert '"result"' in r.text
        assert [rec.getMessage() for rec in caplog.records if rec.name == "plume.mcp.debug"] == (
            expected
        )
