"""Reader MCP tools for reported questions (registered when PLUME_REPORTS is on)."""

import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.types import ToolAnnotations
from starlette.requests import Request

from plume.application.reports.service import ReportedQuestions
from plume.interfaces.http.rate_limit import client_address

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, idempotent_hint=False, open_world_hint=False)

REPORTS_RULE = """\
8. When Plume did not give you what you needed (search_docs found nothing relevant, find_fact
   said found=false, check_call said not_documented for a call you believe is real, or you had
   to answer from your own knowledge), report it: find_reported_questions(api, question) first;
   if one of them is your question, add_to_report(id, note); otherwise report_question(api,
   question, what_was_tried, what_was_missing). Write the question in general terms with no
   user data (no shop ids, order numbers, tokens, names or emails): "how do I refresh an
   expired Shopee access token", not the user's values.
"""

HINT = (
    "If you needed this, you can report the question so maintainers can fix it: "
    "find_reported_questions(api, question), then report_question or add_to_report "
    "(general terms, no user data)."
)


CLIENT_INFO_META = "io.modelcontextprotocol/clientInfo"


@dataclass(frozen=True, slots=True)
class Caller:
    client_name: str | None = None
    session_id: str | None = None  # the mcp-session-id header, when the client sends one
    address: str | None = None  # only for the in-memory hourly limit; never stored


def client_of(ctx: Context | None, trusted_proxy_hops: int = 0) -> Caller:
    """Who is calling. The client name comes from the request's metadata (protocol 2026-07-28:
    every request carries clientInfo), else the initialize handshake (a stateful session), else
    the User-Agent's product token (a legacy client on the stateless reader server, whose tool
    calls carry no clientInfo). Nothing raises: an unknown part is None."""
    if ctx is None:
        return Caller()
    name = session = address = None
    with contextlib.suppress(Exception):
        rc = ctx.request_context
        meta = rc.meta if isinstance(rc.meta, Mapping) else {}
        info = meta.get(CLIENT_INFO_META)
        if isinstance(info, Mapping) and isinstance(info.get("name"), str):
            name = info["name"]
        if name is None:
            params = getattr(rc.session, "client_params", None)
            name = getattr(getattr(params, "client_info", None), "name", None)
        request = rc.request
        if isinstance(request, Request):
            session = request.headers.get("mcp-session-id")
            address = client_address(request, trusted_proxy_hops)
            if name is None:  # a legacy client on a stateless server: its User-Agent product
                agent = request.headers.get("user-agent", "").split(" ", 1)[0]
                name = agent[:64] or None
    return Caller(name if isinstance(name, str) else None, session, address)


def register_report_tools(
    server: MCPServer,
    reports: Callable[[], ReportedQuestions],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    trusted_proxy_hops: int = 0,
) -> None:
    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def find_reported_questions(api: str, question: str) -> dict[str, Any]:
        """Questions about this API that users' assistants already reported Plume could not
        answer: up to 5 similar ones, each with id, question, status (open / answered /
        search-miss / package-gap / out-of-scope, with the reason when closed) and counts.
        Call it before report_question; if one is your question, use add_to_report."""
        return await run(lambda: reports().find(api, question))

    @server.tool(annotations=WRITE, structured_output=True)
    async def report_question(
        ctx: Context,
        api: str,
        question: str,
        what_was_tried: str | None = None,
        what_was_missing: str | None = None,
    ) -> dict[str, Any]:
        """Report a question Plume could not answer, so maintainers fix the search or the
        package. question: the question in GENERAL terms, without user data (no ids, order
        numbers, tokens, names, emails). what_was_tried: the Plume tools and queries you used.
        what_was_missing: what you expected but did not find. At most 1,000 characters each.
        A near-duplicate of an existing report is added to it as a note (the answer says so)."""
        who = client_of(ctx, trusted_proxy_hops)
        return await run(
            lambda: reports().report(
                api, question, what_was_tried, what_was_missing,
                who.client_name, who.session_id, who.address,
            )
        )  # fmt: skip

    @server.tool(annotations=WRITE, structured_output=True)
    async def add_to_report(ctx: Context, id: str, note: str) -> dict[str, Any]:
        """Add a note to a reported question (from find_reported_questions): "also needed
        this", a suggestion, or what else was missing. Raises its report count. No user data;
        at most 1,000 characters."""
        who = client_of(ctx, trusted_proxy_hops)
        return await run(
            lambda: reports().add_note(id, note, who.client_name, who.session_id, who.address)
        )
