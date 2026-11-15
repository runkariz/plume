"""The model view as an MCP App: the ui:// resource, tool metadata, results with and without UI.

Wire format checked against the MCP Apps spec (2026-01-26) and the SDK's mcp.server.apps; see
docs/mcp-apps.md.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.mcp.apps.model_view import APP_MIME_TYPE, MODEL_VIEW_URI, model_view_html
from plume.interfaces.mcp.maintainer_server import (
    McpMaintainerDependencies,
    create_maintainer_server,
)
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
EXTENSION = "io.modelcontextprotocol/ui"
WRITES = {"start_model_session", "submit_model_draft", "revise_model"}
WITH_VIEW = {"submit_model_draft", "get_model"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


def _reader(stack: FakeStack, html: str | None = None) -> Any:
    return create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews,
            search=stack.search,
            get_document=stack.get_document,
            find_fact=stack.find_fact,
            check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds),
            resolver=stack.resolver,
            models=stack.models,
            web_public_url="https://plume.example",
            mcp_app_html=html,
        )
    )


def _text(result: Any) -> str:
    return "".join(c.text for c in result.content if getattr(c, "type", "") == "text")


@pytest.mark.anyio
async def test_resource_is_listed_and_readable_with_the_app_mime(stack: FakeStack) -> None:
    async with Client(_reader(stack)) as client:
        caps = client.server_capabilities
        assert caps is not None
        assert EXTENSION in (caps.extensions or {})
        listed = {r.uri: r for r in (await client.list_resources()).resources}
        view = listed[MODEL_VIEW_URI]
        assert view.mime_type == APP_MIME_TYPE == "text/html;profile=mcp-app"
        assert (view.meta or {}).get("ui", {}).get("prefersBorder") is True
        assert "csp" not in (view.meta or {}).get("ui", {})  # host default: nothing remote
        read = await client.read_resource(MODEL_VIEW_URI)
        content = read.contents[0]
        assert content.mime_type == APP_MIME_TYPE
        assert getattr(content, "text", None) == model_view_html()


@pytest.mark.anyio
async def test_tools_carry_the_ui_metadata(stack: FakeStack) -> None:
    async with Client(_reader(stack)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in WITH_VIEW:
        assert tools[name].meta["ui"]["resourceUri"] == MODEL_VIEW_URI, name  # type: ignore[index]
        # the deprecated flat key too, like the official ext-apps helper (older hosts read it)
        assert tools[name].meta["ui/resourceUri"] == MODEL_VIEW_URI, name  # type: ignore[index]
    for name in WRITES:  # the view can never call a write tool
        assert tools[name].meta["ui"]["visibility"] == ["model"], name  # type: ignore[index]
    for name in ("get_model", "find_fact", "get_document", "search_docs"):
        ui = (tools[name].meta or {}).get("ui", {})
        assert "visibility" not in ui, name  # read tools: model + app (default)


@pytest.mark.anyio
async def test_results_have_structured_model_and_text_with_the_link(stack: FakeStack) -> None:
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    async with Client(_reader(stack)) as client:
        session = await client.call_tool("start_model_session", {"apis": APIS, "concept": "Order"})
        sid = (session.structured_content or {})["session_id"]
        saved = await client.call_tool("submit_model_draft", {"session_id": sid, "draft": draft})
        sc = saved.structured_content or {}
        model = sc["model"]
        assert (sc["visibility"], model["lineage"]["version"]) == ("unlisted", 1)
        link = f"https://plume.example/models/{model['id']}"
        assert model["shareUrl"] == link
        text = _text(saved)  # what Claude Code (no MCP Apps) shows and the model reads
        assert f"Link: {link}" in text
        assert sc["owner_key"] in text
        assert "Keep this key to find or list your model later" in text  # no view declared
        assert "models.json" not in text  # a cloud session can't write files
        assert "Model JSON" not in text  # Claude just wrote it
        assert "refer to it instead of redrawing it" in text
        got = await client.call_tool("get_model", {"snapshot_id": model["id"]})
        assert (got.structured_content or {})["id"] == model["id"]
        logo = (got.structured_content or {})["inputs"][0]["logo"]  # the view draws the tile
        assert logo["color"].startswith("#")
        assert logo["text"]
        assert logo["url"] is None
        full = _text(got)
        assert f"Link: {link}" in full
        assert json.loads(full.split("Model JSON: ", 1)[1])["id"] == model["id"]
        refused = await client.call_tool(
            "submit_model_draft",
            {
                "session_id": sid,
                "draft": json.loads(
                    (DRAFTS / "catalog-order-bad-quote-not-in-doc.json").read_text()
                ),
            },
        )
        assert _text(refused).startswith("Refused: 1 issue(s).")
        assert "QUOTE_NOT_FOUND" in _text(refused)


@pytest.mark.anyio
async def test_maintainer_server_serves_the_view_too(stack: FakeStack) -> None:
    server = create_maintainer_server(
        McpMaintainerDependencies(
            suggest=stack.suggest,
            models=stack.models,
            resolver=stack.resolver,
            tag_build=stack.tag,
            generate=stack.generate,
        )
    )
    async with Client(server) as client:
        assert MODEL_VIEW_URI in {r.uri for r in (await client.list_resources()).resources}
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in ("get_generation", "release_model", "discard_model", "get_model"):
        assert tools[name].meta["ui"]["resourceUri"] == MODEL_VIEW_URI, name  # type: ignore[index]
    for name in ("generate_model", "publish_build", "release_model", "submit_model_draft"):
        assert tools[name].meta["ui"]["visibility"] == ["model"], name  # type: ignore[index]


@pytest.mark.anyio
async def test_bundle_override(stack: FakeStack) -> None:
    async with Client(_reader(stack, "<!doctype html><p>bundle</p>")) as client:
        read = await client.read_resource(MODEL_VIEW_URI)
    assert getattr(read.contents[0], "text", None) == "<!doctype html><p>bundle</p>"


def test_bundle_loads_nothing_remote_and_makes_no_requests() -> None:
    # The packaged file is the web app's React build (web: `npm run build:widget`). React's DOM
    # runtime contains the words innerHTML / textContent internally, so those are not checked
    # here; the web tests check that package text is rendered as text nodes
    # (web/src/widget/widget.test.tsx).
    html = model_view_html()
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert not re.search(r"""url\(\s*["']?(https?:)?//""", html)
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert "@font-face" not in html  # the host's default CSP has no font-src
    for method in ("ui/initialize", "ui/notifications/initialized", "ui/notifications/tool-result"):
        assert method in html


@pytest.mark.anyio
async def test_session_tools_take_model_session_and_the_old_name(stack: FakeStack) -> None:
    """Claude's desktop bridge drops arguments named `session_id`: the tools take
    `model_session` / `set_session`, and still accept the old names."""
    async with Client(_reader(stack)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("get_model_context", "get_model_evidence", "submit_model_draft"):
            schema = tools[name].input_schema
            assert "model_session" in schema["properties"], name
            assert "session_id" not in schema.get("required", []), name
        started = await client.call_tool("start_model_session", {"apis": APIS, "concept": "Order"})
        sid = (started.structured_content or {})["model_session"]
        new = await client.call_tool("get_model_context", {"model_session": sid})
        old = await client.call_tool("get_model_context", {"session_id": sid})
        assert not new.is_error
        assert not old.is_error
        assert (new.structured_content or {})["model_session"] == sid
        missing = await client.call_tool("get_model_context", {})
        assert missing.is_error
        assert "model_session is required" in "".join(
            getattr(c, "text", "") for c in missing.content
        )


def test_view_hint_depends_on_the_client_declaring_apps() -> None:
    from plume.interfaces.mcp.apps.model_view import ui_result  # noqa: PLC0415

    def text(apps: bool) -> str:
        return "".join(
            getattr(c, "text", "") for c in ui_result({}, "Summary.\nModel JSON: {}", apps).content
        )

    shown, unknown = text(True), text(False)
    assert "The user sees this result as an interactive view" in shown
    assert unknown.startswith("Summary.\nIf an interactive view of this result is shown")
    assert unknown.endswith("Model JSON: {}")  # the summary stays first, the JSON last


def test_owner_key_text_points_to_the_view_or_prints_the_key_once() -> None:
    from plume.interfaces.mcp.model_tools import owner_key_text  # noqa: PLC0415

    shown = owner_key_text("pk_secret", view_shown=True)
    assert "pk_secret" not in shown  # the view shows it (structuredContent) with Copy
    assert "shown in the view" in shown
    plain = owner_key_text("pk_secret", view_shown=False)
    assert "pk_secret" in plain
    assert "Keep this key to find or list your model later" in plain
    assert "models.json" not in shown + plain
