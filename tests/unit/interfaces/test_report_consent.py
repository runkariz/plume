# ruff: noqa: E501
"""The user's consent before any report or note is stored: elicitation when the client can ask
(accept / decline / cancel / edit, on both protocols), else user_consent from the LLM; nothing
is stored without a yes, and every row records how the user agreed."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import ElicitRequestParams, ElicitResult

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reports.hosts import ApiHosts
from plume.application.reports.mappings import MappingReports
from plume.application.reports.service import ReportedQuestions
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from plume.interfaces.mcp.report_tools import CONSENT_LINE, NOT_SENT
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.mappings import InMemoryMappings
from tests.fakes.reports import InMemoryReports
from tests.fakes.stack import FakeStack

API = "test-catalog-api"
APIS = [API, "second-catalog-api"]
MODES = ["auto", "legacy"]  # 2026-07-28 (input_required rounds) and the handshake protocol


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


class Env:
    def __init__(self, stack: FakeStack) -> None:
        self.reports, self.mappings = InMemoryReports(), InMemoryMappings()
        hosts = ApiHosts(stack.resolver(), stack.documents)
        self.rq = ReportedQuestions(self.reports, stack.embedder, stack.resolver(), FakeClock(),
                                    enabled=True, salt=b"k", per_hour=1000, hosts=hosts)  # fmt: skip
        self.mr = MappingReports(self.mappings, stack.resolver(), stack.models_repo,
                                 stack.fact_query, stack.documents,
                                 FakeClock(step=timedelta(seconds=1)), enabled=True, salt=b"k",
                                 per_hour=1000, hosts=hosts)  # fmt: skip
        self.server = create_reader_server(McpReaderDependencies(
            overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
            find_fact=stack.find_fact, check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
            models=stack.models, reports=lambda: self.rq, mapping_reports=lambda: self.mr,
        ))  # fmt: skip
        self.asked: list[str] = []

    def client(self, mode: str, answer: dict[str, Any] | None) -> Client:
        """answer None: a client without elicitation; else the user's answer to every ask."""
        if answer is None:
            return Client(self.server, mode=mode)

        async def elicit(_ctx: Any, params: ElicitRequestParams) -> ElicitResult:
            self.asked.append(params.message)
            return ElicitResult(**answer)

        return Client(self.server, mode=mode, elicitation_callback=elicit)  # type: ignore[arg-type]

    def stored(self) -> int:
        return len(self.reports.reports) + len(self.reports.all_notes) + len(
            self.mappings.reports) + len(self.mappings.all_notes)  # fmt: skip


async def _call(client: Client, tool: str, args: dict[str, Any]) -> tuple[bool, Any]:
    res = await client.call_tool(tool, args)
    return res.is_error, (res.structured_content or res.content)


QUESTION = {"api": API, "question": "how do I list orders for john.doe@example.com",
            "what_was_tried": "search_docs list orders"}  # fmt: skip


@pytest.mark.anyio
@pytest.mark.parametrize("mode", MODES)
async def test_accept_shows_the_redacted_text_and_stores_it(stack: FakeStack, mode: str) -> None:
    env = Env(stack)
    async with env.client(mode, {"action": "accept", "content": {"edit": ""}}) as client:
        err, out = await _call(client, "report_question", QUESTION)
    assert not err, out
    assert out["sent"] is True
    (asked,) = env.asked
    assert "Question: how do I list orders for [email]" in asked
    assert "john.doe@example.com" not in asked
    assert "Tried: search_docs list orders" in asked
    assert CONSENT_LINE in asked
    assert API in asked
    (report,) = env.reports.reports.values()
    assert report.consent_method == "elicitation"
    assert report.question == "how do I list orders for [email]"


@pytest.mark.anyio
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("action", ["decline", "cancel"])
async def test_decline_and_cancel_store_nothing(stack: FakeStack, mode: str, action: str) -> None:
    env = Env(stack)
    sid = stack.models().start(APIS, "Order").session_id
    rid = env.rq.report(API, "where is webhook signing documented", None, None)["id"]
    mid = env.mr.report(sid, API, "total", "wrong", "total is wrong")["id"]
    before = env.stored()
    async with env.client(mode, {"action": action}) as client:
        for tool, args in (
            ("report_question", QUESTION),
            ("add_to_report", {"id": rid, "note": "also needed this"}),
            (
                "report_mapping",
                {
                    "model": sid,
                    "api": API,
                    "canonical_field": "currency",
                    "kind": "wrong",
                    "problem": "currency is wrong",
                },
            ),
            ("add_to_mapping_report", {"id": mid, "note": "same here"}),
        ):
            err, out = await _call(client, tool, {**args, "user_consent": "asked_and_approved"})
            assert not err, (tool, out)
            assert out == {"sent": False, "message": NOT_SENT}, tool
    assert len(env.asked) == 4  # the user was asked each time, even with user_consent
    assert env.stored() == before


@pytest.mark.anyio
@pytest.mark.parametrize("mode", MODES)
async def test_an_edit_replaces_the_text_and_is_checked_again(stack: FakeStack, mode: str) -> None:
    env = Env(stack)
    sid = stack.models().start(APIS, "Order").session_id
    edited = {
        "action": "accept",
        "content": {"edit": "how do I list orders for a customer (contact Anja Kowalski)"},
    }
    async with env.client(mode, edited) as client:
        err, out = await _call(client, "report_question", QUESTION)
        assert not err, out
        err, out = await _call(
            client,
            "report_mapping",
            {
                "model": sid,
                "api": API,
                "canonical_field": "total",
                "kind": "missing",
                "problem": "the total has no mapping",
            },
        )
        assert not err, out
    (report,) = env.reports.reports.values()
    assert report.question == "how do I list orders for a customer (contact [name])"  # re-redacted
    (mapping,) = env.mappings.reports.values()
    assert mapping.problem == "how do I list orders for a customer (contact [name])"
    assert mapping.consent_method == "elicitation"
    unsafe = {"action": "accept", "content": {"edit": "[email] [email] [token] [secret]"}}
    async with env.client(mode, unsafe) as client:
        err, out = await _call(client, "report_question", QUESTION)
    assert err  # the edit is validated again: refused, nothing stored
    assert len(env.reports.reports) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("mode", MODES)
async def test_without_elicitation_the_llm_must_attest(stack: FakeStack, mode: str) -> None:
    env = Env(stack)
    sid = stack.models().start(APIS, "Order").session_id
    async with env.client(mode, None) as client:
        err, out = await _call(client, "report_question", QUESTION)
        assert err
        text = str(out)
        assert "ConsentRequiredError: Not sent: ask the user first" in text
        assert "how do I list orders for [email]" in text  # the exact text to show the user
        assert 'user_consent="asked_and_approved"' in text
        err, _ = await _call(
            client,
            "report_mapping",
            {
                "model": sid,
                "api": API,
                "canonical_field": "total",
                "kind": "wrong",
                "problem": "total is wrong",
            },
        )
        assert err
        assert env.stored() == 0
        err, out = await _call(
            client, "report_question", {**QUESTION, "user_consent": "asked_and_approved"}
        )
        assert not err, out
        rid = out["id"]
        err, out = await _call(
            client,
            "add_to_report",
            {"id": rid, "note": "also needed", "user_consent": "asked_and_approved"},
        )
        assert not err, out
        err, out = await _call(
            client,
            "report_mapping",
            {
                "model": sid,
                "api": API,
                "canonical_field": "total",
                "kind": "wrong",
                "problem": "total is wrong",
                "user_consent": "asked_and_approved",
            },
        )
        assert not err, out
        bad = await client.call_tool("report_question", {**QUESTION, "user_consent": "yes"})
        assert bad.is_error  # only the exact value
    (report,) = env.reports.reports.values()
    assert report.consent_method == "llm_attested"
    assert [n.consent_method for n in env.reports.all_notes] == ["llm_attested"]
    assert [r.consent_method for r in env.mappings.reports.values()] == ["llm_attested"]


@pytest.mark.anyio
async def test_a_refused_text_is_refused_before_anyone_is_asked(stack: FakeStack) -> None:
    env = Env(stack)
    async with env.client("auto", {"action": "accept", "content": {"edit": ""}}) as client:
        err, out = await _call(client, "report_question", {"api": API, "question": "x" * 1001})
    assert err
    assert "1000 characters" in str(out)
    assert env.asked == []
    assert env.stored() == 0


@pytest.mark.anyio
async def test_the_consent_parameter_is_not_in_the_schema(stack: FakeStack) -> None:
    env = Env(stack)
    async with env.client("auto", None) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in ("report_question", "add_to_report", "report_mapping", "add_to_mapping_report"):
        props = tools[name].input_schema["properties"]
        assert "consent" not in props
        assert props["user_consent"]["anyOf"][0]["const"] == "asked_and_approved" or "enum" in str(
            props["user_consent"]
        )
