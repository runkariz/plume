"""Phase 3 surfaces: public changes routes, Atom feeds, docsUpdated, model impact, MCP."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.application.test_public_changes import BASE_TEXT, _add_channel, _copy

API = "test-catalog-api"
DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "second-catalog"))
    s.load(str(_copy(packages, tmp_path / "base", BASE_TEXT)))
    return s


def _client(s: FakeStack) -> TestClient:
    return TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews, browse=s.browse, search=s.search,
                get_document=s.get_document, find_fact=s.find_fact, check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds), resolver=s.resolver,
                rate_limit_per_minute=0, suggest=s.suggest, models=s.models,
                collections=s.collections, model_sets=s.model_sets,
                public_changes=s.public_changes, model_impact=s.model_impact,
            )
        )
    )  # fmt: skip


def test_public_routes(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    client = _client(stack)
    assert client.get(f"/v1/apis/{API}").json()["docsUpdated"] is None  # nothing visible yet
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    session = stack.models().start([API, "second-catalog-api"], "Order")
    mid = stack.models().submit(session.session_id, draft).snapshot.snapshot_id
    assert client.get(f"/v1/models/{mid}").json()["impact"]["status"] == "current"
    b = stack.load(str(_copy(packages, tmp_path / "a", BASE_TEXT + " channel: Sales channel.",
                             _add_channel)))  # fmt: skip
    listed = {a["id"]: a for a in client.get("/v1/apis").json()["items"]}
    assert listed[API]["docsUpdated"]["build"] == b
    assert listed["second-catalog-api"]["docsUpdated"] is None
    timeline = client.get(f"/v1/apis/{API}/changes/timeline").json()["items"]
    assert [(t["build"], t["latest"], t["counts"]["confirmed"]) for t in timeline] == [(b, True, 1)]
    page = client.get(f"/v1/apis/{API}/changes", params={"limit": 1}).json()
    assert (page["matched"], page["nextCursor"], page["totals"]["confirmed"]) == (1, None, 1)
    assert page["items"][0]["subject"]["fieldPath"] == "channel"
    assert client.get(f"/v1/apis/{API}/changes", params={"since": "nope"}).status_code == 409
    atom = client.get(f"/v1/apis/{API}/changes.atom")
    assert atom.headers["content-type"].startswith("application/atom+xml")
    assert "property channel added" in atom.text
    assert "channel" in client.get("/v1/changes.atom").text
    model = client.get(f"/v1/models/{mid}").json()
    assert model["impact"] == {"status": "updated_unaffected", "affectedCount": 0,
                               "breakingCount": 0}  # fmt: skip
    full = client.get(f"/v1/models/{mid}/impact").json()
    assert (full["status"], full["affected"]) == ("updated_unaffected", [])


@pytest.mark.anyio
async def test_what_changed_tool(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    stack.load(str(_copy(packages, tmp_path / "a", BASE_TEXT + " channel: Sales channel.",
                         _add_channel)))  # fmt: skip
    server = create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
            find_fact=stack.find_fact, check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
            public_changes=stack.public_changes,
        )
    )  # fmt: skip
    async with Client(server) as client:
        out: dict[str, Any] = (
            await client.call_tool("what_changed", {"api": API})
        ).structured_content or {}
    assert [i["subject"]["fieldPath"] for i in out["items"]] == ["channel"]
    assert "never listed" in out["note"]
