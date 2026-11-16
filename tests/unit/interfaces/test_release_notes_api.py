"""Maintainer HTTP routes and MCP tools for the post-release review."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.maintainer_server import (
    McpMaintainerDependencies,
    create_maintainer_server,
)
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

TOKEN = "pl_release_notes_test"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
API = "test-catalog-api"


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> tuple[FakeStack, str, str]:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path / "data")
    first = s.load(str(packages / "test-catalog"))
    copy = tmp_path / "v2"
    shutil.copytree(packages / "test-catalog", copy)
    path = copy / "connector" / "models" / "order.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["channel"] = {"type": "string", "description": "Sales channel."}
    path.write_text(json.dumps(schema))
    return s, first, s.load(str(copy))


def _client(s: FakeStack) -> TestClient:
    return TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews, browse=s.browse, search=s.search,
                get_document=s.get_document, find_fact=s.find_fact, check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds), resolver=s.resolver,
                rate_limit_per_minute=0, maintainer_tokens=(TOKEN,),
                release_notes=s.release_notes,
            )
        )
    )  # fmt: skip


def test_review_routes(stack: tuple[FakeStack, str, str]) -> None:
    s, first, second = stack
    client = _client(s)
    url = f"/v1/apis/{API}/builds/{second}/release-notes"
    assert client.get(url).status_code == 401  # maintainers only
    notes = client.get(url, headers=AUTH).json()
    assert (notes["review"], notes["tagged"], notes["from"]) == ("pending", True, first)
    assert all({"rule", "title", "explanation", "items"} <= set(g) for g in notes["report"])
    listed = client.get(f"/v1/apis/{API}/release-notes", headers=AUTH).json()["items"]
    assert [n["to"] for n in listed] == [second]
    issues = client.get(f"{url}/issues", headers=AUTH, params={"format": "markdown"})
    assert issues.headers["content-type"].startswith("text/markdown")
    assert f"{first} -> {second}" in issues.text
    assert client.post(f"{url}/rollback", headers=AUTH, json={"reason": ""}).status_code == 422
    rolled = client.post(f"{url}/rollback", headers=AUTH, json={"reason": "extraction bug"})
    assert rolled.json() == {"tag": "latest", "buildId": first, "previous": second,
                             "review": "rolled_back"}  # fmt: skip
    again = client.post(f"{url}/rollback", headers=AUTH, json={"reason": "again"})
    assert (again.status_code, again.json()["error"]) == (409, "invalid_state")
    kept = client.post(f"{url}/keep", headers=AUTH, json={"note": "real docs change"}).json()
    assert kept["review"] == "kept"
    item = next(i for i in kept["items"] if i["subject"]["fieldPath"] == "channel")
    bad = client.post(f"{url}/items/{item['id']}/promote", headers=AUTH, json={"quote": "nope"})
    assert (bad.status_code, bad.json()["code"]) == (422, "QUOTE_NOT_VERIFIED")
    ok = client.post(
        f"{url}/items/{item['id']}/promote", headers=AUTH, json={"quote": "Sales channel."}
    )
    assert ok.json()["class"] == "confirmed"
    assert client.post(f"{url}/items/{item['id']}/demote", headers=AUTH).status_code == 200
    assert (
        client.get(f"/v1/apis/{API}/builds/{first}/release-notes", headers=AUTH).status_code == 404
    )


@pytest.mark.anyio
async def test_maintainer_mcp_tools(stack: tuple[FakeStack, str, str]) -> None:
    s, first, second = stack
    server = create_maintainer_server(
        McpMaintainerDependencies(
            suggest=s.suggest, models=s.models, resolver=s.resolver, tag_build=s.tag,
            release_notes=s.release_notes,
        )
    )  # fmt: skip
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert {"review_release_notes", "keep_release", "rollback_release", "release_issues",
                "promote_change", "demote_change"} <= names  # fmt: skip
        review = (await client.call_tool("review_release_notes", {"api": API})).structured_content
        assert review is not None
        assert (review["to"], review["review"]) == (second, "pending")
        assert "items" not in review
        issues = await client.call_tool("release_issues", {"api": API, "build": second})
        assert first in (issues.structured_content or {})["text"]
        rolled = await client.call_tool(
            "rollback_release", {"api": API, "build": second, "reason": "extraction bug"}
        )
        assert (rolled.structured_content or {})["buildId"] == first
