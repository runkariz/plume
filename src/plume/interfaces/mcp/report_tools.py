"""Reader MCP tools for reported questions (registered when PLUME_REPORTS is on)."""

from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.types import ToolAnnotations

from plume.application.reports.service import ReportedQuestions

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


def client_of(ctx: Context | None) -> tuple[str | None, str | None]:
    """The MCP client's name and the transport session id (None when not known)."""
    if ctx is None:
        return None, None
    name = session = None
    try:
        rc = ctx.request_context
        params = getattr(rc.session, "client_params", None)
        info = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
        name = getattr(info, "name", None)
        request = getattr(rc, "request", None)
        headers = getattr(request, "headers", None)
        session = headers.get("mcp-session-id") if headers is not None else None
    except Exception:  # noqa: S110 - no context (stdio, tests): no client, no session
        pass
    return name, session


def register_report_tools(
    server: MCPServer,
    reports: Callable[[], ReportedQuestions],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
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
        client, session = client_of(ctx)
        return await run(
            lambda: reports().report(
                api, question, what_was_tried, what_was_missing, client, session
            )
        )

    @server.tool(annotations=WRITE, structured_output=True)
    async def add_to_report(ctx: Context, id: str, note: str) -> dict[str, Any]:
        """Add a note to a reported question (from find_reported_questions): "also needed
        this", a suggestion, or what else was missing. Raises its report count. No user data;
        at most 1,000 characters."""
        client, session = client_of(ctx)
        return await run(lambda: reports().add_note(id, note, client, session))
