"""Opt-in MCP request log (PLUME_MCP_DEBUG=1) for host integration problems.

Per JSON-RPC message it logs the method; for `initialize` the client name/version, protocol
version and whether the client declared the MCP Apps extension (capabilities.extensions or the
per-request client capabilities in `_meta`); for `resources/read` of a `ui://` resource its URI;
for `tools/call` the tool name. Never arguments, results, headers or tokens.
"""

import json
import logging
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("plume.mcp.debug")
UI_EXTENSION = "io.modelcontextprotocol/ui"
MAX_BODY = 2_000_000


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_ui(capabilities: Any) -> bool:
    if not isinstance(capabilities, dict):
        return False
    extensions = capabilities.get("extensions")
    return isinstance(extensions, dict) and UI_EXTENSION in extensions


def describe(message: Any) -> str:
    """One log line for one JSON-RPC message (safe fields only)."""
    if not isinstance(message, dict):
        return "non-object message"
    method = message.get("method")
    if not isinstance(method, str):
        return "response" if "result" in message or "error" in message else "unknown message"
    params: dict[str, Any] = _obj(message.get("params"))
    meta = _obj(params.get("_meta"))
    per_request = meta.get("io.modelcontextprotocol/clientCapabilities")
    ui_meta = " ui-in-_meta" if _has_ui(per_request) else ""
    if method == "initialize":
        info = _obj(params.get("clientInfo"))
        return (
            f"initialize client={str(info.get('name'))[:80]!r} "
            f"version={str(info.get('version'))[:40]!r} "
            f"protocol={str(params.get('protocolVersion'))[:20]!r} "
            f"ui_extension={_has_ui(params.get('capabilities'))}{ui_meta}"
        )
    if method == "resources/read":
        uri = str(params.get("uri", ""))
        return f"resources/read {uri[:120] if uri.startswith('ui://') else '(non-ui resource)'}"
    if method == "tools/call":
        return f"tools/call {str(params.get('name'))[:80]}{ui_meta}"
    return f"{method[:80]}{ui_meta}"


class McpDebugLog:
    """ASGI wrapper: reads the request body once, logs, then replays it to the app."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self._app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            body = message.get("body", b"")
            size += len(body)
            if size <= MAX_BODY:
                chunks.append(body)
            more = message.get("more_body", False)
        raw = b"".join(chunks)
        try:
            parsed = json.loads(raw) if raw and size <= MAX_BODY else None
            batch = parsed if isinstance(parsed, list) else [parsed]
            for item in batch:
                if item is not None:
                    logger.info("mcp %s %s", scope.get("path"), describe(item))
        except (ValueError, UnicodeDecodeError):
            logger.info("mcp %s unparsable body (%d bytes)", scope.get("path"), size)
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return await receive()

        await self._app(scope, replay, send)
