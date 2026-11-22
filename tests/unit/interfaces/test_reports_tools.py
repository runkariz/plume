# ruff: noqa: E501
"""Reported questions through MCP and the maintainer API: the redaction corpus through all
three tools, no other tool call stored, hints only when on, status updates by maintainers."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reports.service import ReportedQuestions
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.reports import InMemoryReports
from tests.fakes.stack import FakeStack

API = "test-catalog-api"
TOKEN = "t" * 32

# Things that must never be stored, and the text that carries each of them.
CORPUS = {
    "sk_live_51Habcdefghijklmnop": "my key sk_live_51Habcdefghijklmnop fails",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJl": "the token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJl expired",
    "john.doe@example.com": "the customer john.doe@example.com cannot log in",
    "+31 6 1234 5678": "call the buyer at +31 6 1234 5678 about it",
    "4111 1111 1111 1111": "card 4111 1111 1111 1111 was declined",
    "NL91ABNA0417164300": "refund to NL91ABNA0417164300 failed",
    "123456789012": "order 123456789012 is missing",
    "hunter2": "I set password=hunter2 in the header",
    "ghp_abcdefghij1234567890": "the key ghp_abcdefghij1234567890 is rejected",
    "10.20.30.40": "requests from 10.20.30.40 get 403",
    "SECRETVALUE9": "GET https://shop.example.com/orders?access_token=SECRETVALUE9 fails",
    "abcdefghijklmnop12345": "Authorization: Bearer abcdefghijklmnop12345 gives 401",
    "4567890": "my shop 4567890 cannot list orders",  # 7 digits, no error / code before
    # company names, ids after cue words, customer / warehouse codes (tester, mr-f27160f6c5d5)
    "ACME Handels GmbH": "Our shop ACME Handels GmbH has no low stock mapping",
    "id 4711": "the company id 4711 sees no stock",
    "KD-004711": "customer number KD-004711 has no orders",
    "WH-Hamburg-Nord": "set by hand for warehouse WH-Hamburg-Nord",
    "Nordwind Trading Ltd": "Nordwind Trading Ltd cannot sync stock",
    "AB-77821": "the reference AB-77821 fails",
}


def _stored_text(repo: InMemoryReports) -> str:
    """Everything the repo holds, as one string (every field of reports and notes)."""
    parts = [json.dumps(asdict(r), default=str) for r in repo.reports.values()]
    parts += [json.dumps(asdict(n), default=str) for n in repo.all_notes]
    return "\n".join(parts)


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "test-catalog"))
    return s


def _reports(stack: FakeStack, repo: InMemoryReports) -> ReportedQuestions:
    return ReportedQuestions(repo, stack.embedder, stack.resolver(), FakeClock(), enabled=True,
                             salt=b"k", per_hour=1000)  # fmt: skip


def _server(stack: FakeStack, reports: ReportedQuestions | None) -> Any:
    return create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
            find_fact=stack.find_fact, check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
            reports=(lambda: reports) if reports is not None else None,
        )
    )  # fmt: skip


async def _call(client: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    res = await client.call_tool(tool, args)
    assert not res.is_error, res.content
    return dict(res.structured_content or {})


@pytest.mark.anyio
async def test_the_redaction_corpus_through_all_three_tools(stack: FakeStack) -> None:
    repo = InMemoryReports()
    async with Client(_server(stack, _reports(stack, repo))) as client:
        rid = None
        for i, (_, text) in enumerate(CORPUS.items()):
            general = f"case {i}: why does this request fail"
            out = await _call(client, "report_question", {
                "api": API, "question": f"{general} when {text}",
                "what_was_tried": f"search_docs '{text}'", "what_was_missing": text,
            })  # fmt: skip
            rid = rid or out["id"]
            await _call(client, "add_to_report", {"id": rid, "note": f"also: {text}"})
            await _call(client, "find_reported_questions", {"api": API, "question": text})
    stored = _stored_text(repo)
    assert repo.reports, "the reports were stored"
    for secret in CORPUS:
        assert secret not in stored, secret
    assert "Authorization" not in stored or "[token]" in stored


@pytest.mark.anyio
async def test_no_other_tool_call_is_stored(stack: FakeStack) -> None:
    repo = InMemoryReports()
    async with Client(_server(stack, _reports(stack, repo))) as client:
        await _call(client, "list_apis", {})
        hits = await _call(client, "search_docs", {"api": API, "query": "list orders john@x.com"})
        doc = hits["results"][0]["doc_id"]
        await _call(client, "get_document", {"api": API, "doc_id": doc})
        await _call(client, "find_fact", {"api": API, "name": "no_such_field_xyz"})
        await _call(client, "check_call", {"api": API, "method": "GET", "path": "/nope/123"})
    assert repo.reports == {}
    assert repo.all_notes == []


@pytest.mark.anyio
async def test_hints_and_instructions_only_when_reporting_is_on(stack: FakeStack) -> None:
    on, off = _server(stack, _reports(stack, InMemoryReports())), _server(stack, None)
    assert "report_question" in (on.instructions or "")
    assert "report_question" not in (off.instructions or "")
    async with Client(on) as client:
        fact = await _call(client, "find_fact", {"api": API, "name": "no_such_field_xyz"})
        call = await _call(client, "check_call", {"api": API, "method": "GET", "path": "/nope"})
        assert "report_question" in fact["report_hint"]
        assert "report_question" in call["report_hint"]
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {"find_reported_questions", "report_question", "add_to_report"} <= tools
    async with Client(off) as client:
        fact = await _call(client, "find_fact", {"api": API, "name": "no_such_field_xyz"})
        assert "report_hint" not in fact
        tools = {t.name for t in (await client.list_tools()).tools}
        assert "report_question" not in tools


@pytest.mark.anyio
async def test_a_near_duplicate_is_merged_and_said_so(stack: FakeStack) -> None:
    repo = InMemoryReports()
    async with Client(_server(stack, _reports(stack, repo))) as client:
        first = await _call(client, "report_question",
                            {"api": API, "question": "how do I refresh an access token"})  # fmt: skip
        found = await _call(client, "find_reported_questions",
                            {"api": API, "question": "refresh an access token"})  # fmt: skip
        assert found["similar"][0]["id"] == first["id"]
        again = await _call(client, "report_question",
                            {"api": API, "question": "How do I refresh an access token?"})  # fmt: skip
        assert again["merged"] is True
        assert again["id"] == first["id"]
    assert len(repo.reports) == 1


def test_maintainers_list_read_and_label_reports(stack: FakeStack) -> None:
    repo = InMemoryReports()
    svc = _reports(stack, repo)
    rid = svc.report(API, "where is webhook signing documented", "search_docs webhook", None)["id"]
    svc.add_note(rid, "also needed the header name")
    client = TestClient(create_app(HttpDependencies(
        overviews=stack.overviews, browse=stack.browse, search=stack.search,
        get_document=stack.get_document, find_fact=stack.find_fact, check_call=stack.check_call,
        list_builds=lambda: ListBuilds(stack.builds, stack.tags),
        diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
        rate_limit_per_minute=0, maintainer_tokens=(TOKEN,), reports=lambda: svc,
    )))  # fmt: skip
    assert client.get("/v1/maintainer/reports").status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    listed = client.get("/v1/maintainer/reports", params={"api": API}, headers=auth).json()
    assert [r["id"] for r in listed["reports"]] == [rid]
    assert listed["enabled"] is True
    preflight = client.options(
        f"/v1/maintainer/reports/{rid}",
        headers={"Origin": "http://127.0.0.1:18473", "Access-Control-Request-Method": "PATCH"},
    )
    assert "PATCH" in preflight.headers.get("access-control-allow-methods", "")
    one = client.get(f"/v1/maintainer/reports/{rid}", headers=auth).json()
    assert one["notes"][0]["text"] == "also needed the header name"
    done = client.patch(f"/v1/maintainer/reports/{rid}", headers=auth,
                        json={"status": "package-gap", "reason": "not in the package"})  # fmt: skip
    assert done.json()["status"] == "package-gap"
    bad = client.patch(f"/v1/maintainer/reports/{rid}", headers=auth, json={"status": "maybe"})
    assert bad.status_code == 422
