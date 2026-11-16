"""Canonical-model MCP tools, shared by the reader MCP (anyone: models are stored UNLISTED and
readable by whoever has the id) and the maintainer MCP (models are stored UNRELEASED until
release_model; server-side generation)."""

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.apps import client_supports_apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from mcp_types import CallToolResult

from plume.application.errors import ApplicationError
from plume.application.models.collections import Collections
from plume.application.models.generate import GenerateModels
from plume.application.models.impact import ModelImpact, widget_rows
from plume.application.models.impact import summary as impact_summary
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
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
        "usage": job.usage,
    }


def _leaf_count(model: dict[str, Any]) -> int:
    def count(fields: list[dict[str, Any]]) -> int:
        return sum(count(f["fields"]) if f.get("fields") else 1 for f in fields)

    return count(model.get("fields", []))


def apps_shown(ctx: Context) -> bool:
    """Whether the client declared MCP Apps (the host renders the view)."""
    try:
        return client_supports_apps(ctx)
    except Exception:  # no session info (stateless request): unknown
        return False


def session_arg(primary: str | None, alias: str | None, name: str) -> str:
    """The session id from the new parameter name or its old alias. Claude's desktop bridge
    drops arguments named `session_id`, hence `model_session` / `set_session`."""
    value = (primary or alias or "").strip()
    if not value:
        raise ToolError(f"{name} is required (the id returned when the session started)")
    return value


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
        f"{_leaf_count(model)} fields; coverage {coverage}; "
        f"{len(model.get('openQuestions', []))} open question(s); every citation checked "
        f"({model.get('citations', {}).get('checked', 0)}). Generated, unverified.",
    ]
    if model.get("stale"):
        lines.append("STALE: a pinned build is no longer the API's latest (see staleInputs).")
    if model.get("supersededBy"):
        lines.append(f"SUPERSEDED by {model['supersededBy']} (kept readable; not listed).")
    warned = model.get("warnings") or []
    if warned:
        lines.append(
            f"{len(warned)} warning(s): "
            + "; ".join(f"{w['field']} ({w['api']}): {w['code']}" for w in warned[:10])
            + (" …" if len(warned) > 10 else "")
            + ". WRITE_ONLY_SOURCE: the mapping cites only a request/write; check whether the "
            "docs have a read source."
        )
    if link:
        lines.append(f"Link: {link}")
    if full:
        lines.append("Model JSON: " + json.dumps(model, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def _collection_id(value: str) -> str:
    """A collection id, also from its pasted URL (…/mine/c-…)."""
    return value.strip().rstrip("/").rsplit("/", 1)[-1]


def submit_text(out: dict[str, Any]) -> str:
    if not out.get("accepted"):
        issues = json.dumps(out.get("issues", []), ensure_ascii=False)
        return f"Refused: {len(out.get('issues', []))} issue(s). {out.get('next', '')}\n{issues}"
    text = ("Stored" if out.get("created") else "Already stored") + f" ({out['stored_as']}). "
    text += model_text(out["model"])
    return text + payloads.collection_text(out.get("collection"))


def register_model_tools(  # noqa: PLR0915
    server: MCPServer,
    models: Callable[[], ModelSessions],
    resolver: Callable[[], BuildResolver],
    run: Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]],
    maintainer: bool,
    web_public_url: str | None = None,
    generate: Callable[[], GenerateModels] | None = None,
    related: Callable[[], SuggestRelated] | None = None,
    collections: Callable[[], Collections] | None = None,
    sets: Callable[[], ModelSets] | None = None,
    impact: Callable[[], ModelImpact] | None = None,
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
        if impact is not None:  # the view has no network: the summary and a few rows
            full = impact().of_model(snap)
            body["impact"] = impact_summary(full) | {
                "rows": widget_rows(full),
                "impactUrl": f"/v1/models/{snap.snapshot_id}/impact",
            }
        return body

    def list_item(m: ModelSnapshot) -> dict[str, Any]:
        service = models()
        versions = service.lineage_info(m, maintainer)["versions"]
        out = payloads.model_list_item(m, service.stale_inputs(m), versions)
        if impact is not None:
            out["impact"] = impact_summary(impact().of_model(m))
        return out

    if related is not None:
        rel = related

        @server.tool(annotations=READ, structured_output=True)
        async def suggest_related(
            apis: list[str], concept: str, limit: int = 24, offset: int = 0
        ) -> dict[str, Any]:
            """Concepts related to one concept (e.g. Product -> Variant, Image), with relation
            candidates from documented evidence only, cited per API, and the designs the evidence
            supports (embedded / reference, cardinality). The USER chooses the design: offer the
            options and ask; never decide silently. `aliases` (different names at the same
            documented position, e.g. variant / variation) are only offers for the user."""
            return await run(
                lambda: payloads.related_payload(rel().execute(apis, concept, limit, offset))
            )

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def start_model_session(apis: list[str], concept: str) -> dict[str, Any]:
        """Pin the latest build of 2..6 APIs for one concept (e.g. "Order"). Returns
        session_id. To change an existing model use revise_model instead."""

        def go() -> dict[str, Any]:
            s = models().start(apis, concept, origin)
            return {
                "model_session": s.session_id,
                "session_id": s.session_id,
                "concept": s.concept,
                "inputs": [{"api": i.api, "build": i.build} for i in s.inputs],
                "next": "Call get_model_context(model_session).",
            }

        return await run(go)

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_context(
        model_session: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        """Index of the evidence: per API the concept's documents with field counts, plus the
        draft format and the citation rules. Read the fields with get_model_evidence."""
        sid = session_arg(model_session, session_id, "model_session")
        return await run(lambda: models().context(sid))

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_evidence(
        api: str,
        model_session: str | None = None,
        doc_ids: list[str] | None = None,
        cursor: int = 0,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Fields (path, type, location, required, description) of the concept's documents in
        one API of the session, at most ~20k characters per call. Follow next_cursor until null.
        Copy paths exactly into the draft and quote descriptions verbatim as evidence."""
        sid = session_arg(model_session, session_id, "model_session")
        return await run(lambda: models().evidence(sid, api, doc_ids, cursor))

    stored_as = "unreleased (a maintainer releases it)" if maintainer else "unlisted"

    @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
    async def submit_model_draft(
        ctx: Context,
        draft: dict[str, Any],
        model_session: str | None = None,
        based_on: str | None = None,
        session_id: str | None = None,
        collection: str | None = None,
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Submit the canonical model (JSON as in draft_format). Plume checks every citation.
        Accepted -> a stored model; refused -> issues with codes (MISSING_CITATION,
        QUOTE_NOT_FOUND, FIELD_NOT_FOUND, ...): fix them and submit again. based_on (a model id)
        makes it the next version of that model. collection: the user's "My models" link id
        (c-...) from an earlier save in this conversation; omit only for the first save (a new
        link is returned)."""

        sid = session_arg(model_session, session_id, "model_session")

        def go() -> dict[str, Any]:
            try:
                result = models().submit(
                    sid, draft, based_on, maintainer, collection=None if maintainer else collection
                )
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
            link = payloads.collection_payload(result.collection, web_public_url)
            if link:
                out["collection"] = link
                out["note"] = (
                    "Give the user the model link and their My models link; pass "
                    f"collection={link['id']!r} on every later save in this conversation."
                )
            return out

        out = await run(go)
        return ui_result(out, submit_text(out), apps_shown(ctx))

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_session(
        model_session: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        """A session's state: status submitted + snapshot_id once a draft was accepted."""
        sid = session_arg(model_session, session_id, "model_session")
        return await run(lambda: models().session_status(sid))

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
    async def revise_model(snapshot_id: str) -> dict[str, Any]:
        """Change a model: opens a session on the CURRENT builds with the model as
        starting_draft. Edit it (keep citations verbatim), then submit_model_draft(model_session,
        draft, based_on=snapshot_id) to store a new version (models stay immutable)."""
        return await run(lambda: models().revise(snapshot_id, maintainer))

    @server.tool(annotations=READ, structured_output=True, meta=UI_META)
    async def get_model(
        ctx: Context, snapshot_id: str
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """A stored canonical model with its versions (lineage) and link. Every citation was
        checked; the content is generated, unverified."""
        model = await run(lambda: model_json(models().visible_snapshot(snapshot_id, maintainer)))
        return ui_result(model, model_text(model, full=True), apps_shown(ctx))

    if maintainer:

        @server.tool(name="list_models", annotations=READ, structured_output=True)
        async def list_all_models(
            api: str | None = None, visibility: str = "all"
        ) -> dict[str, Any]:
            """Models newest first. visibility: official | unreleased | unlisted | discarded |
            superseded | all."""

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
        async def release_model(
            ctx: Context, snapshot_id: str, supersedes: list[str] | None = None
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            """Make an unreleased model official (listed publicly). supersedes: ids of official
            models of the same concept this one replaces (see list_supersedable_models; ASK
            the maintainer, never decide): they stay readable by id but leave the lists."""
            wanted = list(dict.fromkeys(supersedes or []))
            model = await run(lambda: model_json(models().release(snapshot_id, wanted)))
            model["supersedes"] = wanted
            text = model_text(model)
            if wanted:
                text += f"\nSuperseded: {', '.join(wanted)}."
            return ui_result(model, text, apps_shown(ctx))

        @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
        async def supersede_models(
            ctx: Context, snapshot_id: str, supersedes: list[str]
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            """An OFFICIAL model retires older official models of its concept (ids from
            list_supersedable_models; ASK the maintainer, never decide): they stay readable by
            id with supersededBy, and leave the lists."""
            wanted = list(dict.fromkeys(supersedes))
            model = await run(lambda: model_json(models().supersede(snapshot_id, wanted)))
            model["supersedes"] = wanted
            text = model_text(model) + f"\nSuperseded: {', '.join(wanted)}."
            return ui_result(model, text, apps_shown(ctx))

        @server.tool(annotations=READ, structured_output=True)
        async def list_supersedable_models(snapshot_id: str) -> dict[str, Any]:
            """Official models of the same concept (any API set) that releasing this model may
            supersede; covered = their APIs are a subset of this model's. Offer them to the
            maintainer before release_model(..., supersedes=[...])."""

            def go() -> dict[str, Any]:
                service = models()
                return {"items": service.supersedable(service.snapshot(snapshot_id))}

            return await run(go)

        @server.tool(annotations=WRITE, structured_output=True, meta=UI_WRITE_META)
        async def discard_model(
            ctx: Context, snapshot_id: str
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            """Throw away an unreleased model."""
            model = await run(lambda: model_json(models().discard(snapshot_id)))
            return ui_result(model, model_text(model), apps_shown(ctx))

        if generate is not None:
            gen = generate

            @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
            async def generate_model(apis: list[str], concept: str) -> dict[str, Any]:
                """Plume writes the model itself with its LLM (same validation; a few repair
                rounds). Returns a job; poll get_generation(job_id). The result is unreleased."""
                return await run(lambda: job_payload(gen().start(apis, concept)))

            @server.tool(annotations=READ, structured_output=True, meta=UI_META)
            async def get_generation(
                ctx: Context, job_id: str
            ) -> Annotated[CallToolResult, dict[str, Any]]:
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
                return ui_result(out, text, apps_shown(ctx))

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
        async def list_my_models(
            collection: str | None = None, owner_keys: list[str] | None = None
        ) -> dict[str, Any]:
            """The user's own models and sets: the latest version of each in their "My models"
            link (collection id c-..., or its URL). owner_keys: old per-model keys (transition):
            their models and the My models links they became."""

            def go() -> dict[str, Any]:
                if collection:
                    if collections is None:
                        raise ApplicationError("My models links are not configured")
                    return collection_json(collections().content(_collection_id(collection)))
                keys = owner_keys or []
                if not keys:
                    raise ApplicationError("pass collection (or old owner_keys)")
                links = collections().for_owner_keys(keys) if collections else []
                return {
                    "models": [list_item(m) for m in models().mine(keys)],
                    "collections": [
                        {"id": c, "url": payloads.collection_url(c, web_public_url)} for c in links
                    ],
                    "next": "Use list_my_models(collection) from now on.",
                }

            return await run(go)

        @server.tool(annotations=WRITE, structured_output=True)
        async def merge_my_models(collection: str, sources: list[str]) -> dict[str, Any]:
            """Move every model and set of the other My models links (sources) into this one,
            for a user who ended up with several. The old links then list nothing."""
            if collections is None:
                raise ToolError("My models links are not configured")
            merging = collections
            return await run(
                lambda: collection_json(
                    merging().merge(
                        _collection_id(collection), [_collection_id(x) for x in sources]
                    )
                )
            )

        def collection_json(c: Any) -> dict[str, Any]:
            set_items = []
            if sets is not None:
                service = sets()
                set_items = [
                    {
                        **payloads.set_list_item(
                            x, service.stale_inputs(x), service.lineage_info(x, False)["versions"]
                        ),
                        "newerVersion": payloads.newer_version(
                            c.newer.get(x.set_id), "set", web_public_url
                        ),
                    }
                    for x in c.sets
                ]
            return {
                "collection": {
                    "id": c.collection_id,
                    "url": payloads.collection_url(c.collection_id, web_public_url),
                },
                "mergedInto": c.merged_into,
                "models": [
                    {
                        **list_item(m),
                        "newerVersion": payloads.newer_version(
                            c.newer.get(m.snapshot_id), "model", web_public_url
                        ),
                    }
                    for m in c.models
                ],
                "sets": set_items,
            }
