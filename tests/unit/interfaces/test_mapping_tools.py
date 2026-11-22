# ruff: noqa: E501
"""Mapping reports through MCP and the maintainer API: the redaction corpus through all three
tools, no other tool call stored (model tools included), the tools and rule only when on,
maintainers list, read, accept / reject / route, and see verified mappings."""

import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reports.hosts import ApiHosts
from plume.application.reports.mappings import MappingReports
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.mappings import InMemoryMappings
from tests.fakes.stack import FakeStack
from tests.unit.interfaces.test_reports_tools import CORPUS

API = "test-catalog-api"
APIS = [API, "second-catalog-api"]
TOKEN = "t" * 32
GOOD: dict[str, Any] = {"paths": ["total"], "fetch": "GET /api/{version}/orders",
        "evidence": [{"doc_id": "model:order", "quote": "Total monetary amount billed for the order."}]}  # fmt: skip


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


def _svc(stack: FakeStack, repo: InMemoryMappings) -> MappingReports:
    return MappingReports(repo, stack.resolver(), stack.models_repo, stack.fact_query,
                          stack.documents, FakeClock(step=timedelta(seconds=1)), enabled=True,
                          salt=b"k", per_hour=1000,
                          hosts=ApiHosts(stack.resolver(), stack.documents))  # fmt: skip


def _stored(repo: InMemoryMappings) -> str:
    parts = [json.dumps(asdict(r), default=str) for r in repo.reports.values()]
    parts += [json.dumps(asdict(n), default=str) for n in repo.all_notes]
    return "\n".join(parts)


def _server(stack: FakeStack, svc: MappingReports | None) -> Any:
    return create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
            find_fact=stack.find_fact, check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
            models=stack.models,
            mapping_reports=(lambda: svc) if svc is not None else None,
        )
    )  # fmt: skip


async def _call(client: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    res = await client.call_tool(tool, args)
    assert not res.is_error, res.content
    return dict(res.structured_content or {})


@pytest.mark.anyio
async def test_the_redaction_corpus_through_all_three_tools(stack: FakeStack) -> None:
    repo = InMemoryMappings()
    sid = stack.models().start(APIS, "Order").session_id
    async with Client(_server(stack, _svc(stack, repo))) as client:
        rid = None
        for i, (_, text) in enumerate(CORPUS.items()):
            out = await _call(client, "report_mapping", {
                "model": sid, "api": API, "canonical_field": f"field{i}", "kind": "wrong",
                "problem": f"case {i}: the mapping is wrong when {text}",
                "current_mapping": f"maps {text}",
            })  # fmt: skip
            rid = rid or out["id"]
            await _call(client, "add_to_mapping_report", {"id": rid, "note": f"also: {text}"})
            await _call(
                client, "find_mapping_reports", {"model": sid, "api": API, "field": f"field{i}"}
            )
    stored = _stored(repo)
    assert len(repo.reports) == len(CORPUS)
    for secret in CORPUS:
        assert secret not in stored, secret


@pytest.mark.anyio
async def test_no_other_tool_call_is_stored(stack: FakeStack) -> None:
    repo = InMemoryMappings()
    async with Client(_server(stack, _svc(stack, repo))) as client:
        started = await _call(client, "start_model_session", {"apis": APIS, "concept": "Order"})
        sid = started["model_session"]
        await _call(client, "get_model_context", {"model_session": sid})
        await _call(client, "get_model_evidence", {"model_session": sid, "api": API})
        await client.call_tool(
            "submit_model_draft", {"model_session": sid, "draft": {"name": "Order"}}
        )
        await _call(client, "search_docs", {"api": API, "query": "order total john@x.com"})
        await _call(client, "find_mapping_reports", {"model": sid, "api": API})
    assert repo.reports == {}
    assert repo.all_notes == []
    assert repo.mappings == {}


@pytest.mark.anyio
async def test_tools_and_rule_only_when_on(stack: FakeStack) -> None:
    on, off = _server(stack, _svc(stack, InMemoryMappings())), _server(stack, None)
    assert "report_mapping" in (on.instructions or "")
    assert "report_mapping" not in (off.instructions or "")
    async with Client(on) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {"find_mapping_reports", "report_mapping", "add_to_mapping_report"} <= tools
        sid = (await _call(client, "start_model_session", {"apis": APIS, "concept": "Order"}))[
            "model_session"
        ]
        refused = await _call(client, "report_mapping", {
            "model": sid, "api": API, "canonical_field": "total", "kind": "missing",
            "problem": "no mapping for the total", "suggested_mapping": {**GOOD, "paths": ["nope_xyz"]},
        })  # fmt: skip
        assert refused["validation"]["ok"] is False
    async with Client(off) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert "report_mapping" not in tools


def test_maintainers_list_read_accept_and_see_verified_mappings(stack: FakeStack) -> None:
    repo = InMemoryMappings()
    svc = _svc(stack, repo)
    sid = stack.models().start(APIS, "Order").session_id
    rid = svc.report(sid, API, "grandTotal", "missing", "the total has no mapping", None, GOOD)[
        "id"
    ]
    bad = svc.report(
        sid, API, "tax", "wrong", "tax is wrong", "taxes", {**GOOD, "paths": ["nope_xyz"]}
    )["id"]
    svc.add_note(rid, "also needed this")
    client = TestClient(create_app(HttpDependencies(
        overviews=stack.overviews, browse=stack.browse, search=stack.search,
        get_document=stack.get_document, find_fact=stack.find_fact, check_call=stack.check_call,
        list_builds=lambda: ListBuilds(stack.builds, stack.tags),
        diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
        rate_limit_per_minute=0, maintainer_tokens=(TOKEN,), mapping_reports=lambda: svc,
    )))  # fmt: skip
    assert client.get("/v1/maintainer/mapping-reports").status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    listed = client.get(
        "/v1/maintainer/mapping-reports", params={"api": API, "concept": "order"}, headers=auth
    ).json()
    assert [r["id"] for r in listed["reports"]] == [rid, bad]  # most reported first
    assert listed["enabled"] is True
    first = listed["reports"][0]
    assert first["canonicalField"] == "grandTotal"
    assert first["suggestion"]["evidence"][0] == {
        "docId": "model:order",
        "quote": GOOD["evidence"][0]["quote"],
        "noQuote": None,
    }
    assert first["validation"] == {"ok": True, "reason": None}
    second = listed["reports"][1]
    assert second["suggestion"] is None
    assert second["validation"]["ok"] is False
    assert second["currentMapping"] == "taxes"
    one = client.get(f"/v1/maintainer/mapping-reports/{rid}", headers=auth).json()
    assert one["notes"][0]["text"] == "also needed this"
    refused = client.patch(f"/v1/maintainer/mapping-reports/{bad}", headers=auth,
                           json={"action": "accept", "reason": "ok"})  # fmt: skip
    assert refused.status_code == 400
    assert "report_refused" in refused.text
    routed = client.patch(f"/v1/maintainer/mapping-reports/{bad}", headers=auth,
                          json={"action": "route", "route": "stream", "reason": "not in package"}).json()  # fmt: skip
    assert (routed["status"], routed["route"]) == ("routed", "stream")
    done = client.patch(f"/v1/maintainer/mapping-reports/{rid}", headers=auth,
                        json={"action": "accept", "reason": "matches the docs"}).json()  # fmt: skip
    assert done["status"] == "accepted"
    assert done["verified"]["suspended"] is False
    by_name = client.get(
        "/v1/maintainer/verified-mappings", params={"concept": "Orders"}, headers=auth
    ).json()
    assert [m["reportId"] for m in by_name["mappings"]] == [rid]  # a model's concept name works
    vm = client.get("/v1/maintainer/verified-mappings", params={"api": API}, headers=auth).json()
    assert [(m["canonicalField"], m["paths"], m["reportId"]) for m in vm["mappings"]] == [
        ("grandTotal", ["total"], rid)
    ]
    assert (
        client.patch(
            f"/v1/maintainer/mapping-reports/{rid}", headers=auth, json={"action": "maybe"}
        ).status_code
        == 422
    )
