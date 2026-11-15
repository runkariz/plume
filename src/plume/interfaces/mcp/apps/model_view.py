"""The canonical-model view as an MCP App (io.modelcontextprotocol/ui), see docs/mcp-apps.md.

One `ui://` HTML resource, served as ``text/html;profile=mcp-app`` on the reader and maintainer
MCP servers. Tools that return a model point at it with ``_meta.ui.resourceUri``; hosts that
support MCP Apps (Claude web / Desktop) render it inline and pass it the tool result, other hosts
(Claude Code) show the text content: a summary with the share link.

The HTML is one self-contained file (the web app's mapping view built with everything inlined,
or the packaged placeholder until that exists). No `_meta.ui.csp` is declared, so hosts apply the
spec's default policy: no remote scripts, styles, images, fonts or connections.
"""

from importlib import resources
from pathlib import Path
from typing import Any

from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp_types import CallToolResult, TextContent

MODEL_VIEW_URI = "ui://plume/model-view"
UI_META: dict[str, Any] = {"ui": {"resourceUri": MODEL_VIEW_URI}}
# Tools the view must never call (writes): hosts reject app-originated calls to tools whose
# visibility lacks "app". Read-only tools keep the default (model + app).
MODEL_ONLY_META: dict[str, Any] = {"ui": {"visibility": ["model"]}}
UI_WRITE_META: dict[str, Any] = {"ui": {"resourceUri": MODEL_VIEW_URI, "visibility": ["model"]}}

__all__ = ["APP_MIME_TYPE", "MODEL_VIEW_URI", "model_view_apps", "model_view_html"]


def model_view_html(path: Path | None = None) -> str:
    """The bundle: ``path`` when given (e.g. PLUME_MCP_APP_HTML), else the packaged file."""
    if path is not None:
        return path.read_text(encoding="utf-8")
    return resources.files(__package__).joinpath("model-view.html").read_text(encoding="utf-8")


def model_view_apps(html: str) -> Apps:
    """The Apps extension with the model view resource (advertises the capability)."""
    apps = Apps()
    apps.add_html_resource(
        MODEL_VIEW_URI,
        html,
        name="model-view",
        title="Plume canonical model",
        description="The canonical model's mapping across its APIs, with coverage and versions.",
        prefers_border=True,
    )
    return apps


def ui_result(structured: dict[str, Any], text: str) -> CallToolResult:
    """A result for UI-bound tools: ``text`` for the model and text-only hosts, the data for
    the view in ``structuredContent``."""
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=structured
    )
