"""Model set MCP tools (reader and maintainer): several models with relations the USER designs."""

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

from plume.application.errors import ApplicationError
from plume.application.models.model_sets import ModelSets
from plume.application.models.sessions import ModelDraftRefusedError
from plume.application.reader.resolve import BuildResolver
from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import Visibility
from plume.interfaces import payloads
from plume.interfaces.mcp.apps.model_view import (
    MODEL_ONLY_META,
    UI_META,
    UI_WRITE_META,
    ui_result,
)
from plume.interfaces.mcp.model_tools import READ, WRITE


def set_text(x: dict[str, Any], full: bool = False) -> str:
    """What the model and text-only hosts read: members, relations (decided or not), link."""
    lineage = x.get("lineage") or {}
    lines = [
        f"Model set {x['name']} {x['id']}: {x['visibility']}, version {lineage.get('version', 1)} "
        f"of {lineage.get('versions', 1)}, across {', '.join(i['id'] for i in x['inputs'])}.",
        "Members: " + "; ".join(f"{m['concept']} ({m['modelId']})" for m in x["members"]) + ".",
    ]
    for r in x["relations"]:
        how = (
            f"embedded via {r['from']}.{r['embed']['field']}"
            if r["embed"]
            else f"reference {r['from']}.{r['ref']['field']} -> {r['to']}.{r['ref']['key']}"
        )
        apis = ", ".join(f"{a}: {v or 'not documented'}" for a, v in r["support"].items())
        state = "decided by the user" if r["confirmed"] else "UNDECIDED: ask the user"
        lines.append(f"- {r['from']} -> {r['to']} {r['cardinality']}, {how} ({state}; {apis})")
    if x.get("stale"):
        lines.append("STALE: a pinned build is no longer the API's latest.")
    link = x.get("shareUrl") or x.get("sharePath")
    if link:
        lines.append(f"Link: {link}")
    if full:
        lines.append("Set JSON: " + json.dumps(x, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def register_set_tools(  # noqa: PLR0915
    server: MCPServer,
    sets: Callable[[], ModelSets],
    resolver: Callable[[], BuildResolver],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    maintainer: bool,
    web_public_url: str | None = None,
) -> None:
    origin = "maintainer" if maintainer else "user"

    def names(x: ModelSetSnapshot) -> dict[str, str]:
        out = {}
        for i in x.inputs:
            try:
                out[i.api] = resolver().resolve(i.api).api.name
            except ApplicationError:
                out[i.api] = i.api
        return out

    def set_json(x: ModelSetSnapshot) -> dict[str, Any]:
        service = sets()
        return payloads.set_payload(
            x,
            service.member_models(x),
            service.lineage_info(x, maintainer),
            service.stale_inputs(x),
            names(x),
            web_public_url,
        )

    def item(x: ModelSetSnapshot) -> dict[str, Any]:
        service = sets()
        return payloads.set_list_item(
            x, service.stale_inputs(x), service.lineage_info(x, maintainer)["versions"]
        )

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def start_set_session(apis: list[str], concepts: list[str]) -> dict[str, Any]:
        """Start a model SET (several models with relations, e.g. Product + Variant + Image):
        pins the builds of 2..6 APIs once and opens one model session per concept (1..8). Next:
        get_set_context(set_session_id)."""

        def go() -> dict[str, Any]:
            x = sets().start(apis, concepts, origin)
            return {
                "set_session_id": x.session_id,
                "inputs": [{"api": i.api, "build": i.build} for i in x.inputs],
                "member_sessions": dict(x.member_sessions),
                "next": "Call get_set_context(set_session_id).",
            }

        return await run(go)

    @server.tool(annotations=READ, structured_output=True)
    async def get_set_context(set_session_id: str) -> dict[str, Any]:
        """Per member: its model session, evidence index and reusable models; plus relation
        candidates (documented evidence only) and aliases. ASK THE USER how each relation should
        be designed (embedded or reference, cardinality); never decide silently."""
        return await run(lambda: sets().context(set_session_id, maintainer))

    @server.tool(annotations=READ, structured_output=True)
    async def get_set_session(set_session_id: str) -> dict[str, Any]:
        """A set session's state: submitted + set_id once a set was accepted."""
        return await run(lambda: sets().session_status(set_session_id))

    @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
    async def submit_model_set(
        set_session_id: str, draft: dict[str, Any], based_on: str | None = None
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Submit the set (members by model id + relations the user decided; undecided ones as
        confirmed:false). Plume checks the members, that relation fields exist in them, and every
        relation citation. based_on (a set id) makes it the next version of that set."""

        def go() -> dict[str, Any]:
            try:
                result = sets().submit(set_session_id, draft, based_on, maintainer)
            except ModelDraftRefusedError as exc:
                return payloads.refusal_payload(exc.issues)
            x = result.snapshot
            out: dict[str, Any] = {
                "accepted": True,
                "created": result.created,
                "set_id": x.set_id,
                "visibility": x.visibility,
                "version": x.version,
                "set": set_json(x),
            }
            if result.owner_key:
                out["owner_key"] = result.owner_key
            return out

        out = await run(go)
        if not out.get("accepted"):
            issues = json.dumps(out.get("issues", []), ensure_ascii=False)
            return ui_result(out, f"Refused: {len(out.get('issues', []))} issue(s).\n{issues}")
        text = ("Stored" if out["created"] else "Already stored") + ". " + set_text(out["set"])
        if out.get("owner_key"):
            text += (
                f"\nowner_key: {out['owner_key']} (shown once; save it with set_id "
                f"{out['set_id']} in ~/.plume/models.json; do not show it in the chat)"
            )
        return ui_result(out, text)

    @server.tool(annotations=READ, structured_output=True, meta=UI_META)
    async def get_model_set(set_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
        """A model set: members (get_model for each), relations with per-API evidence, versions,
        link."""
        x = await run(lambda: set_json(sets().visible(set_id, maintainer)))
        return ui_result(x, set_text(x, full=True))

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def revise_model_set(set_id: str) -> dict[str, Any]:
        """Change a set: a set session on the CURRENT builds with the set as starting_draft.
        Revise stale members, ask the user about relation changes, then submit_model_set(...,
        based_on=set_id)."""
        return await run(lambda: sets().revise(set_id, maintainer))

    if maintainer:

        @server.tool(name="list_model_sets", annotations=READ, structured_output=True)
        async def list_all_sets(api: str | None = None, visibility: str = "all") -> dict[str, Any]:
            """Model sets newest first. visibility: official | unreleased | unlisted | all."""

            def go() -> dict[str, Any]:
                wanted = Visibility.ALL if visibility == "all" else (visibility,)
                if any(v not in Visibility.ALL for v in wanted):
                    raise ApplicationError(f"unknown visibility {visibility!r}")
                return {"sets": [item(x) for x in sets().list(api, 50, wanted)]}

            return await run(go)

        @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
        async def release_model_set(set_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            """Make an unreleased set official, releasing its unreleased member models with it
            (listed in released_members). Refused while a relation is undecided."""

            def go() -> dict[str, Any]:
                r = sets().release(set_id)
                return {"set": set_json(r.snapshot), "released_members": list(r.released_members)}

            out = await run(go)
            members = ", ".join(out["released_members"]) or "none"
            return ui_result(
                out, f"Released. Members released with it: {members}.\n" + set_text(out["set"])
            )

        @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
        async def discard_model_set(set_id: str) -> dict[str, Any]:
            """Throw away an unreleased set (its members are kept)."""
            return await run(lambda: set_json(sets().discard(set_id)))

    else:

        @server.tool(name="list_model_sets", annotations=READ, structured_output=True)
        async def list_official_sets(api: str | None = None) -> dict[str, Any]:
            """Official model sets, newest first."""
            return await run(lambda: {"sets": [item(x) for x in sets().list(api)]})

        @server.tool(annotations=READ, structured_output=True)
        async def list_my_model_sets(owner_keys: list[str]) -> dict[str, Any]:
            """The user's own sets (owner keys from submit_model_set, kept locally)."""
            return await run(lambda: {"sets": [item(x) for x in sets().mine(owner_keys)]})
