"""Canonical-model MCP tools, shared by the reader MCP (anyone: models are stored UNLISTED and
readable by whoever has the id) and the maintainer MCP (models are stored UNRELEASED until
release_model; server-side generation)."""

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from mcp_types import CallToolResult

from plume.application.errors import ApplicationError
from plume.application.models.generate import GenerateModels
from plume.application.models.sessions import (
    ModelDraftRefusedError,
    ModelSessions,
)
from plume.application.ports.model_repo import ModelJob
from plume.application.reader.resolve import BuildResolver
from plume.domain.models.snapshot import ModelSnapshot, Origin, Visibility
from plume.interfaces import payloads
from plume.interfaces.mcp.apps.model_view import (
    MODEL_ONLY_META,
    UI_META,
    UI_WRITE_META,
    ui_result,
)


def _annotations(read_only: bool) -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=False,
        idempotent_hint=read_only,
        open_world_hint=False,
    )


READ = _annotations(True)
WRITE = _annotations(False)


def job_payload(job: ModelJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "apis": list(job.apis),
        "concept": job.concept,
        "session_id": job.session_id,
        "round": job.round,
        "max_rounds": job.max_rounds,
        "snapshot_id": job.snapshot_id,
        "error": job.error,
        "generator": job.generator,
    }


def model_text(model: dict[str, Any], full: bool = False) -> str:
    """What the model (and hosts without MCP Apps, e.g. Claude Code) read: a summary, the
    link, and with ``full`` the model JSON itself."""
    lineage = model.get("lineage") or {}
    apis = [i["id"] for i in model.get("inputs", [])]
    coverage = ", ".join(
        f"{api} {c['mapped']}/{c['total']}" for api, c in (model.get("coverage") or {}).items()
    )
    link = model.get("shareUrl") or model.get("sharePath")
    lines = [
        f"{model['name']} ({model['concept']}) model {model['id']}: {model.get('visibility')}, "
        f"version {lineage.get('version', 1)} of {lineage.get('versions', 1)}, across "
        f"{', '.join(apis)}.",
        f"{len(model.get('fields', []))} fields; coverage {coverage}; "
        f"{len(model.get('openQuestions', []))} open question(s); every citation checked "
        f"({model.get('citations', {}).get('checked', 0)}). Generated, unverified.",
    ]
    if model.get("stale"):
        lines.append("STALE: a pinned build is no longer the API's latest (see staleInputs).")
    if link:
        lines.append(f"Link: {link}")
    if full:
        lines.append("Model JSON: " + json.dumps(model, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def submit_text(out: dict[str, Any]) -> str:
    if not out.get("accepted"):
        issues = json.dumps(out.get("issues", []), ensure_ascii=False)
        return f"Refused: {len(out.get('issues', []))} issue(s). {out.get('next', '')}\n{issues}"
    text = ("Stored" if out.get("created") else "Already stored") + f" ({out['stored_as']}). "
    text += model_text(out["model"])
    if out.get("owner_key"):
        text += (
            f"\nowner_key: {out['owner_key']} (shown once; save it with snapshot_id "
            f"{out['snapshot_id']} in ~/.plume/models.json; do not show it in the chat)"
        )
    return text


def register_model_tools(  # noqa: PLR0915
    server: MCPServer,
    models: Callable[[], ModelSessions],
    resolver: Callable[[], BuildResolver],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    maintainer: bool,
    web_public_url: str | None = None,
    generate: Callable[[], GenerateModels] | None = None,
) -> None:
    origin = Origin.MAINTAINER if maintainer else Origin.USER

    def names(snap: ModelSnapshot) -> dict[str, str]:
        out = {}
        for i in snap.inputs:
            try:
                out[i.api] = resolver().resolve(i.api).api.name
            except ApplicationError:
                out[i.api] = i.api
        return out

    def model_json(snap: ModelSnapshot) -> dict[str, Any]:
        service = models()
        body = payloads.snapshot_payload(snap, names(snap), service.stale_inputs(snap))
        body.update(
            payloads.access_payload(snap, service.lineage_info(snap, maintainer), web_public_url)
        )
        return body

    def list_item(m: ModelSnapshot) -> dict[str, Any]:
        service = models()
        versions = service.lineage_info(m, maintainer)["versions"]
        return payloads.model_list_item(m, service.stale_inputs(m), versions)

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def start_model_session(apis: list[str], concept: str) -> dict[str, Any]:
        """Pin the latest build of 2..6 APIs for one concept (e.g. "Order"). Returns
        session_id. To change an existing model use revise_model instead."""

        def go() -> dict[str, Any]:
            s = models().start(apis, concept, origin)
            return {
                "session_id": s.session_id,
                "concept": s.concept,
                "inputs": [{"api": i.api, "build": i.build} for i in s.inputs],
                "next": "Call get_model_context(session_id).",
            }

        return await run(go)

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_context(session_id: str) -> dict[str, Any]:
        """Index of the evidence: per API the concept's documents with field counts, plus the
        draft format and the citation rules. Read the fields with get_model_evidence."""
        return await run(lambda: models().context(session_id))

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_evidence(
        session_id: str, api: str, doc_ids: list[str] | None = None, cursor: int = 0
    ) -> dict[str, Any]:
        """Fields (path, type, location, required, description) of the concept's documents in
        one API of the session, at most ~20k characters per call. Follow next_cursor until null.
        Copy paths exactly into the draft and quote descriptions verbatim as evidence."""
        return await run(lambda: models().evidence(session_id, api, doc_ids, cursor))

    stored_as = "unreleased (a maintainer releases it)" if maintainer else "unlisted"

    @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
    async def submit_model_draft(
        session_id: str, draft: dict[str, Any], based_on: str | None = None
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Submit the canonical model (JSON as in draft_format). Plume checks every citation.
        Accepted -> a stored model; refused -> issues with codes (MISSING_CITATION,
        QUOTE_NOT_FOUND, FIELD_NOT_FOUND, ...): fix them and submit again. based_on (a model id)
        makes it the next version of that model."""

        def go() -> dict[str, Any]:
            try:
                result = models().submit(session_id, draft, based_on, maintainer)
            except ModelDraftRefusedError as exc:
                return payloads.refusal_payload(exc.issues)
            snap = result.snapshot
            body = model_json(snap)
            out: dict[str, Any] = {
                "accepted": True,
                "created": result.created,
                "snapshot_id": snap.snapshot_id,
                "visibility": snap.visibility,
                "version": snap.version,
                "share_url": body["shareUrl"],
                "share_path": body["sharePath"],
                "model": body,
                "stored_as": stored_as,
            }
            if result.owner_key:
                out["owner_key"] = result.owner_key
                out["note"] = (
                    "Save owner_key with the snapshot_id (e.g. in ~/.plume/models.json): it is "
                    "shown only once and is what list_my_models needs. Give the user the link."
                )
            return out

        out = await run(go)
        return ui_result(out, submit_text(out))

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_session(session_id: str) -> dict[str, Any]:
        """A session's state: status submitted + snapshot_id once a draft was accepted."""
        return await run(lambda: models().session_status(session_id))

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def revise_model(snapshot_id: str) -> dict[str, Any]:
        """Change a model: opens a session on the CURRENT builds with the model as
        starting_draft. Edit it (keep citations verbatim), then submit_model_draft(session_id,
        draft, based_on=snapshot_id) to store a new version (models stay immutable)."""
        return await run(lambda: models().revise(snapshot_id, maintainer))

    @server.tool(annotations=READ, structured_output=True, meta=UI_META)
    async def get_model(snapshot_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
        """A stored canonical model with its versions (lineage) and link. Every citation was
        checked; the content is generated, unverified."""
        model = await run(lambda: model_json(models().visible_snapshot(snapshot_id, maintainer)))
        return ui_result(model, model_text(model, full=True))

    if maintainer:

        @server.tool(name="list_models", annotations=READ, structured_output=True)
        async def list_all_models(
            api: str | None = None, visibility: str = "all"
        ) -> dict[str, Any]:
            """Models newest first. visibility: official | unreleased | unlisted | all."""

            def go() -> dict[str, Any]:
                wanted = Visibility.ALL if visibility == "all" else (visibility,)
                if any(v not in Visibility.ALL for v in wanted):
                    raise ApplicationError(f"unknown visibility {visibility!r}")
                return {
                    "models": [list_item(m) for m in models().list(api, 50, wanted)],
                    "note": payloads.STALE_HINT,
                }

            return await run(go)

        @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
        async def release_model(snapshot_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            """Make an unreleased model official (listed publicly)."""
            model = await run(lambda: model_json(models().release(snapshot_id)))
            return ui_result(model, model_text(model))

        @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
        async def discard_model(snapshot_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            """Throw away an unreleased model."""
            model = await run(lambda: model_json(models().discard(snapshot_id)))
            return ui_result(model, model_text(model))

        if generate is not None:
            gen = generate

            @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
            async def generate_model(apis: list[str], concept: str) -> dict[str, Any]:
                """Plume writes the model itself with its LLM (same validation; a few repair
                rounds). Returns a job; poll get_generation(job_id). The result is unreleased."""
                return await run(lambda: job_payload(gen().start(apis, concept)))

            @server.tool(annotations=READ, structured_output=True, meta=UI_META)
            async def get_generation(job_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
                """A generation job: status queued|running|succeeded|failed, snapshot_id; the
                model itself once it succeeded."""

                def go() -> dict[str, Any]:
                    out = job_payload(gen().get(job_id))
                    if out["snapshot_id"]:
                        snap = models().visible_snapshot(out["snapshot_id"], maintainer)
                        out["model"] = model_json(snap)
                    return out

                out = await run(go)
                text = f"Generation {out['job_id']}: {out['status']}"
                if out.get("error"):
                    text += f" ({out['error']})"
                if "model" in out:
                    text += "\n" + model_text(out["model"])
                return ui_result(out, text)

    else:

        @server.tool(name="list_models", annotations=READ, structured_output=True)
        async def list_official_models(api: str | None = None) -> dict[str, Any]:
            """Official canonical models, newest first (reuse one instead of regenerating)."""

            def go() -> dict[str, Any]:
                return {
                    "models": [list_item(m) for m in models().list(api)],
                    "note": payloads.STALE_HINT,
                }

            return await run(go)

        @server.tool(annotations=READ, structured_output=True)
        async def list_my_models(owner_keys: list[str]) -> dict[str, Any]:
            """The user's own models: the latest version of each model started with one of
            these owner keys (from submit_model_draft; keep them locally)."""
            return await run(lambda: {"models": [list_item(m) for m in models().mine(owner_keys)]})
