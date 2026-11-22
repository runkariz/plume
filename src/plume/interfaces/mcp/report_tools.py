"""Reader MCP tools for reported questions (registered when PLUME_REPORTS is on)."""

import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.requests import Request

from plume.application.errors import ApplicationError
from plume.application.reports.mappings import MappingReports
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
   expired Shopee access token", not the user's values. ASK THE USER FIRST: these tools store
   text. When Plume asks the user itself (your client supports elicitation), just call the tool.
   Otherwise show the user the exact text you will send and that "Plume's maintainers use this
   to improve results; kept up to 90 days; only maintainers can read it", ask whether to send
   it, and only on a yes call the tool with user_consent="asked_and_approved".
"""

HINT = (
    "If you needed this, you can report the question so maintainers can fix it: "
    "find_reported_questions(api, question), then report_question or add_to_report "
    "(general terms, no user data; ask the user before sending)."
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


CONSENT_LINE = (
    "Plume's maintainers use this to improve results; kept up to 90 days; only maintainers can "
    "read it."
)
APPROVED = "asked_and_approved"
NOT_SENT = "not sent (the user declined)"
Consent = Literal["asked_and_approved"] | None
_CONSENT_DOC = (
    'user_consent: "asked_and_approved" only after you showed the user the exact text and they '
    "said yes; not needed when Plume asks the user itself (elicitation)."
)


class ConsentForm(BaseModel):
    """What the user may change before the report is sent."""

    edit: str = Field(
        default="",
        max_length=1000,
        description="Optional: a corrected text for the main field shown above (the question, "
        "problem or note); leave empty to send it as shown. It is checked again before sending.",
    )


class _NoAsk:
    """The resolver's answer when Plume cannot ask the user (no elicitation, or the text is
    refused anyway: the tool body then reports the refusal and stores nothing)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


def _can_elicit(ctx: Context) -> bool:
    """The client declared form elicitation (a bare `elicitation: {}` counts as form)."""
    try:
        caps = ctx.client_capabilities
    except Exception:
        return False
    e = caps.elicitation if caps is not None else None
    return e is not None and (e.form is not None or e.url is None)


def _ask(ctx: Context, preview: Callable[[], dict[str, Any]], labels: dict[str, str]) -> Any:
    """Elicit the user's consent over the exact text to store, or _NoAsk."""
    if not _can_elicit(ctx):
        return _NoAsk("no_elicitation")
    try:
        shown = preview()
    except ApplicationError as exc:
        return _NoAsk(str(exc))
    lines = [f"Plume would store this report about {shown['api']}:", ""]
    lines += [f"{label}: {shown[key]}" for key, label in labels.items() if shown.get(key)]
    lines += ["", CONSENT_LINE, "Accept to send it; decline to send nothing."]
    return Elicit("\n".join(lines), ConsentForm)


async def _with_consent(
    outcome: ElicitationResult[ConsentForm],
    user_consent: str | None,
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    preview: Callable[[], dict[str, Any]],
    store: Callable[[str | None, str], dict[str, Any]],
) -> dict[str, Any]:
    """Store only with the user's yes: elicited (accept; an edit replaces the main text), or,
    when Plume cannot ask, attested by the LLM (user_consent). Otherwise nothing is stored."""
    if not isinstance(outcome, AcceptedElicitation):
        return {"sent": False, "message": NOT_SENT}
    data = outcome.data
    if isinstance(data, _NoAsk):
        if data.reason != "no_elicitation":
            return await run(preview)  # the same refusal the store would give; nothing stored
        if user_consent != APPROVED:

            def refuse() -> dict[str, Any]:
                shown = preview()
                raise ConsentRequiredError(shown)

            return await run(refuse)
        return await run(lambda: {"sent": True, **store(None, "llm_attested")})
    edit = data.edit.strip() if isinstance(data, ConsentForm) else ""
    return await run(lambda: {"sent": True, **store(edit or None, "elicitation")})


class ConsentRequiredError(ApplicationError):
    def __init__(self, shown: dict[str, Any]) -> None:
        text = "; ".join(f"{k}: {v}" for k, v in shown.items() if v and k != "api")
        super().__init__(
            "Not sent: ask the user first. Show them exactly what Plume would store "
            f"({text}) and say: {CONSENT_LINE} Only if they say yes, call again with "
            f'user_consent="{APPROVED}".'
        )


_QUESTION_LABELS = {"question": "Question", "what_was_tried": "Tried",
                    "what_was_missing": "Missing"}  # fmt: skip
_NOTE_LABELS = {"report_id": "Report", "note": "Note"}
_MAPPING_LABELS = {"concept": "Model", "canonical_field": "Field", "kind": "Kind",
                   "problem": "Problem", "current_mapping": "Current mapping",
                   "suggested_mapping": "Suggested mapping"}  # fmt: skip


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

    def ask_question(
        ctx: Context, api: str, question: str, what_was_tried: str | None,
        what_was_missing: str | None,
    ) -> Any:  # fmt: skip
        return _ask(ctx, lambda: reports().preview(api, question, what_was_tried,
                                                   what_was_missing), _QUESTION_LABELS)  # fmt: skip

    @server.tool(annotations=WRITE, structured_output=True)
    async def report_question(
        ctx: Context,
        api: str,
        question: str,
        consent: Annotated[ElicitationResult[ConsentForm], Resolve(ask_question)],
        what_was_tried: str | None = None,
        what_was_missing: str | None = None,
        user_consent: Consent = None,
    ) -> dict[str, Any]:
        """Report a question Plume could not answer, so maintainers fix the search or the
        package. Stores text: the user must agree first (Plume asks them itself when the
        client supports it; otherwise show them the exact text and pass user_consent).
        question: the question in GENERAL terms, without user data (no ids, order numbers,
        tokens, names, emails). what_was_tried: the Plume tools and queries you used.
        what_was_missing: what you expected but did not find. At most 1,000 characters each.
        A near-duplicate of an existing report is added to it as a note (the answer says so).
        """
        who = client_of(ctx, trusted_proxy_hops)

        def store(edit: str | None, method: str) -> dict[str, Any]:
            return reports().report(
                api, edit or question, what_was_tried, what_was_missing, who.client_name,
                who.session_id, who.address, consent_method=method,
            )  # fmt: skip

        return await _with_consent(
            consent, user_consent, run,
            lambda: reports().preview(api, question, what_was_tried, what_was_missing), store,
        )  # fmt: skip

    def ask_note(ctx: Context, id: str, note: str) -> Any:
        return _ask(ctx, lambda: reports().preview_note(id, note), _NOTE_LABELS)

    @server.tool(annotations=WRITE, structured_output=True)
    async def add_to_report(
        ctx: Context,
        id: str,
        note: str,
        consent: Annotated[ElicitationResult[ConsentForm], Resolve(ask_note)],
        user_consent: Consent = None,
    ) -> dict[str, Any]:
        """Add a note to a reported question (from find_reported_questions): "also needed
        this", a suggestion, or what else was missing. Raises its report count. No user data;
        at most 1,000 characters. Stores text: the user must agree first (as report_question).
        """
        who = client_of(ctx, trusted_proxy_hops)

        def store(edit: str | None, method: str) -> dict[str, Any]:
            return reports().add_note(id, edit or note, who.client_name, who.session_id,
                                      who.address, consent_method=method)  # fmt: skip

        return await _with_consent(
            consent, user_consent, run, lambda: reports().preview_note(id, note), store
        )


MAPPINGS_RULE = """\
9. Canonical models: when the user says a suggested mapping is wrong, had to map a field by
   hand, found in the docs a source for a canonical field that has none, or the model lacks a
   field all the selected APIs have, report it: find_mapping_reports(model, api, field) first;
   if one matches, add_to_mapping_report(id, note); otherwise report_mapping(...). A
   suggested_mapping is checked like a draft (the path must exist in that API, the quote must
   be in the cited document); one that fails is kept only as the problem. General terms, no
   user data. verified_mappings in get_model_context come from accepted reports: use them first.
   These tools store text too: ask the user first, as in rule 8 (user_consent).
"""


def register_mapping_tools(
    server: MCPServer,
    mappings: Callable[[], MappingReports],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    trusted_proxy_hops: int = 0,
) -> None:
    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def find_mapping_reports(
        model: str, api: str, field: str | None = None
    ) -> dict[str, Any]:
        """Mapping reports users' assistants already sent for a canonical model's concept on one
        API (model: a model session id or a model id; field: a canonical field, optional): up
        to 5, each with id, kind, status (with the reason once decided) and count, plus the
        verified mappings maintainers accepted. Call it before report_mapping."""
        return await run(lambda: mappings().find(model, api, field))

    def ask_mapping(
        ctx: Context, model: str, api: str, canonical_field: str, kind: str, problem: str,
        current_mapping: str | None, suggested_mapping: dict[str, Any] | None,
    ) -> Any:  # fmt: skip
        return _ask(ctx, lambda: mappings().preview(model, api, canonical_field, kind, problem,
                                                    current_mapping, suggested_mapping),
                    _MAPPING_LABELS)  # fmt: skip

    @server.tool(annotations=WRITE, structured_output=True)
    async def report_mapping(
        ctx: Context,
        model: str,
        api: str,
        canonical_field: str,
        kind: str,
        problem: str,
        consent: Annotated[ElicitationResult[ConsentForm], Resolve(ask_mapping)],
        current_mapping: str | None = None,
        suggested_mapping: dict[str, Any] | None = None,
        user_consent: Consent = None,
    ) -> dict[str, Any]:
        """Report a wrong or missing canonical-model mapping. model: the model session id or
        model id. kind: wrong | missing | model-field-missing (the model lacks a field the APIs
        have). problem: what is wrong, in GENERAL terms (no user data). current_mapping: the
        mapping as it is now, in words. suggested_mapping (optional): the source on that API as
        in a draft: {"paths": ["..."], "evidence": [{"doc_id": "...", "quote": "..."}],
        "fetch"?: "..."}, or, when the field is NOT available on that API, {"notAvailable":
        true, "notFrom": ["the wrong path"], "evidence": [{"doc_id": "...", "quote": "what that
        path really is"}]}; Plume validates it like submit_model_draft and keeps it only when it
        passes (else the answer gives the validator's reason). The same field and kind already
        reported adds your report as a note. At most 1,000 characters per text field. Stores
        text: the user must agree first (as report_question)."""
        who = client_of(ctx, trusted_proxy_hops)

        def store(edit: str | None, method: str) -> dict[str, Any]:
            return mappings().report(
                model, api, canonical_field, kind, edit or problem, current_mapping,
                suggested_mapping, who.client_name, who.session_id, who.address,
                consent_method=method,
            )  # fmt: skip

        return await _with_consent(
            consent, user_consent, run,
            lambda: mappings().preview(model, api, canonical_field, kind, problem,
                                       current_mapping, suggested_mapping), store,
        )  # fmt: skip

    def ask_mapping_note(ctx: Context, id: str, note: str) -> Any:
        return _ask(ctx, lambda: mappings().preview_note(id, note), _NOTE_LABELS)

    @server.tool(annotations=WRITE, structured_output=True)
    async def add_to_mapping_report(
        ctx: Context,
        id: str,
        note: str,
        consent: Annotated[ElicitationResult[ConsentForm], Resolve(ask_mapping_note)],
        user_consent: Consent = None,
    ) -> dict[str, Any]:
        """Add a note (+1) to a mapping report from find_mapping_reports: "also wrong for us",
        or what the mapping should be. No user data; at most 1,000 characters. Stores text:
        the user must agree first (as report_question)."""
        who = client_of(ctx, trusted_proxy_hops)

        def store(edit: str | None, method: str) -> dict[str, Any]:
            return mappings().add_note(id, edit or note, who.client_name, who.session_id,
                                       who.address, consent_method=method)  # fmt: skip

        return await _with_consent(
            consent, user_consent, run, lambda: mappings().preview_note(id, note), store
        )
