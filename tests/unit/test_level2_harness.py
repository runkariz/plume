"""The Level 2 harness itself, on a recorded stream (no Claude call, no stack)."""

import json
import stat
from pathlib import Path

from tests.live_claude.harness import Run, Stack, ToolCall, check_reader, mcp_config, parse_stream


def _line(obj: object) -> str:
    return json.dumps(obj)


STREAM = [
    _line({"type": "system", "subtype": "init"}),
    _line(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "mcp__plume__find_fact",
                        "input": {"api": "shopify", "name": "loyalty_points"},
                    }
                ]
            },
        }
    ),
    _line(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {"found": False, "complete": True, "build": "b-1"}
                                ),
                            }
                        ],
                    }
                ]
            },
        }
    ),
    _line(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "mcp__plume__get_document",
                        "input": {"api": "shopify", "doc_id": "model:customer"},
                    }
                ]
            },
        }
    ),
    _line(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": json.dumps({"source_url": "https://shopify.dev/customer"}),
                    }
                ]
            },
        }
    ),
    "not json",
    _line(
        {
            "type": "result",
            "result": "loyalty_points is not documented in build b-1 "
            "(https://shopify.dev/customer).",
            "total_cost_usd": 0.12,
            "num_turns": 4,
        }
    ),
]


def test_parse_stream() -> None:
    run = parse_stream(STREAM, "q")
    assert [c.name for c in run.calls] == ["mcp__plume__find_fact", "mcp__plume__get_document"]
    assert run.calls[0].result == {"found": False, "complete": True, "build": "b-1"}
    assert run.cost_usd == 0.12
    assert run.turns == 4
    assert run.tool("get_document")[0].input["doc_id"] == "model:customer"


def test_reader_checks_pass_and_fail() -> None:
    run = parse_stream(STREAM, "q")
    assert all(c.passed for c in check_reader(run, "shopify"))
    unproven = Run(
        "q", 0, "This field is not documented.", [ToolCall("mcp__plume__search_docs", {})]
    )
    names = {c.name: c.passed for c in check_reader(unproven, "shopify")}
    assert names["'not documented' backed by find_fact(complete=true)"] is False
    assert names["the answer cites Plume documents"] is False


def test_mcp_config_is_private_and_removed(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("pl_secret_for_test\n")
    stack = Stack("http://a", "http://m/mcp", "http://m/maintainer/mcp", token)
    with mcp_config(stack) as cfg:
        data = json.loads(cfg.read_text())
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
        assert data["mcpServers"]["plume-maintainer"]["headers"]["Authorization"].endswith(
            "pl_secret_for_test"
        )
        assert data["mcpServers"]["plume"] == {"type": "http", "url": "http://m/mcp"}
    assert not cfg.exists()
