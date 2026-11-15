"""Maintainer MCP server (bearer token): canonical-model sessions and build/tag control.

Claude generates canonical models here: start_model_session -> get_model_context (the evidence
pack) -> write the model -> submit_model_draft. Plume validates every citation against the
pinned builds and stores an immutable snapshot, or refuses with precise issue codes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from plume import __version__
from plume.application.jobs.maintainer import MaintainerJobs, job_payload
from plume.application.knowledge.tag_build import TagBuild
from plume.application.models.concepts import SuggestConcepts
from plume.application.models.sessions import ModelDraftRefusedError, ModelSessions
from plume.application.reader.resolve import BuildResolver
from plume.domain.shared.ids import BuildId
from plume.interfaces import payloads
from plume.interfaces.mcp.reader_server import _run

INSTRUCTIONS = """\
Plume maintainer tools. Canonical models across 2..N APIs:
1. suggest_concepts(apis) to see which concepts the APIs share (coverage per API).
2. start_model_session(apis, concept) pins the latest build of each API.
3. get_model_context(session_id) returns a compact index (per API the concept's documents
   with field counts), the draft format and the rules. Then get_model_evidence(session_id,
   api) per API returns the fields with descriptions, page by page (follow next_cursor; pass
   doc_ids to read other documents of the pinned build).
4. Write the model, then submit_model_draft(session_id, draft). Plume checks every citation
   (document exists, quote is in it, field and endpoint exist). A refusal lists issue codes;
   fix and resubmit. An accepted draft becomes an immutable snapshot (status
   generated_unverified): get_model(id).
Build control: publish_build(api, build, tag) moves a tag (refused when the quality gate
failed); get_job(job_id) reads a maintainer job.
"""

WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


@dataclass(frozen=True, slots=True)
class McpMaintainerDependencies:
    suggest: Callable[[], SuggestConcepts]
    models: Callable[[], ModelSessions]
    resolver: Callable[[], BuildResolver]
    tag_build: Callable[[], TagBuild]
    jobs: Callable[[], MaintainerJobs] | None = None


def _names(resolver: BuildResolver, apis: list[str]) -> dict[str, str]:
    out = {}
    for a in apis:
        try:
            out[a] = resolver.resolve(a).api.name
        except Exception:
            out[a] = a
    return out


def create_maintainer_server(deps: McpMaintainerDependencies) -> MCPServer:
    server = MCPServer(
        name="plume-maintainer",
        title="Plume maintainer",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    @server.tool(annotations=READ, structured_output=True)
    async def suggest_concepts(apis: list[str]) -> dict[str, Any]:
        """Concepts shared by 2..6 APIs (deterministic), with coverage per API."""
        return await _run(lambda: payloads.suggestions_payload(deps.suggest().execute(apis)))

    @server.tool(annotations=WRITE, structured_output=True)
    async def start_model_session(apis: list[str], concept: str) -> dict[str, Any]:
        """Pin the latest build of each API for one concept (e.g. "Order"). Returns session_id."""

        def run() -> dict[str, Any]:
            s = deps.models().start(apis, concept)
            return {
                "session_id": s.session_id,
                "concept": s.concept,
                "inputs": [{"api": i.api, "build": i.build} for i in s.inputs],
                "next": "Call get_model_context(session_id).",
            }

        return await _run(run)

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_context(session_id: str) -> dict[str, Any]:
        """Index of the evidence: per API the concept's documents with field counts, plus the
        draft format and the citation rules. Read the fields with get_model_evidence."""
        return await _run(lambda: deps.models().context(session_id))

    @server.tool(annotations=READ, structured_output=True)
    async def get_model_evidence(
        session_id: str, api: str, doc_ids: list[str] | None = None, cursor: int = 0
    ) -> dict[str, Any]:
        """Fields (path, type, location, required, description) of the concept's documents in
        one API of the session, at most ~20k characters per call. Follow next_cursor until null.
        Copy paths exactly into the draft and quote descriptions verbatim as evidence."""
        return await _run(lambda: deps.models().evidence(session_id, api, doc_ids, cursor))

    @server.tool(annotations=WRITE, structured_output=True)
    async def submit_model_draft(session_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        """Submit the canonical model (JSON as in draft_format). Accepted -> snapshot; refused ->
        issues with codes (MISSING_CITATION, QUOTE_NOT_FOUND, FIELD_NOT_FOUND, ...)."""

        def run() -> dict[str, Any]:
            try:
                result = deps.models().submit(session_id, draft)
            except ModelDraftRefusedError as exc:
                return payloads.refusal_payload(exc.issues)
            snap = result.snapshot
            names = _names(deps.resolver(), [i.api for i in snap.inputs])
            return {
                "accepted": True,
                "created": result.created,
                "snapshot_id": snap.snapshot_id,
                "model": payloads.snapshot_payload(snap, names),
            }

        return await _run(run)

    @server.tool(annotations=READ, structured_output=True)
    async def get_model(snapshot_id: str) -> dict[str, Any]:
        """A stored canonical model snapshot."""

        def run() -> dict[str, Any]:
            snap = deps.models().snapshot(snapshot_id)
            return payloads.snapshot_payload(
                snap, _names(deps.resolver(), [i.api for i in snap.inputs])
            )

        return await _run(run)

    @server.tool(annotations=READ, structured_output=True)
    async def list_models(api: str | None = None) -> dict[str, Any]:
        """Stored model snapshots (newest first), optionally for one API."""
        return await _run(
            lambda: {
                "models": [
                    {
                        "snapshot_id": m.snapshot_id,
                        "name": m.draft.name,
                        "concept": m.concept,
                        "apis": [i.api for i in m.inputs],
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in deps.models().list(api)
                ]
            }
        )

    @server.tool(annotations=WRITE, structured_output=True)
    async def publish_build(api: str, build: str, tag: str = "latest") -> dict[str, Any]:
        """Move a tag to a sealed build of the API (publish or roll back)."""

        def run() -> dict[str, Any]:
            b = deps.resolver().resolve(api, build).build
            r = deps.tag_build().execute(BuildId(b.build_id.value), tag)
            return {
                "api": api,
                "tag": r.tag,
                "build": r.build_id.value,
                "previous": r.previous.value if r.previous else None,
            }

        return await _run(run)

    if deps.jobs is not None:
        jobs = deps.jobs

        @server.tool(annotations=READ, structured_output=True)
        async def get_job(job_id: str) -> dict[str, Any]:
            """A maintainer job (upload/review/build/publish state, diff, plan, eval)."""
            return await _run(lambda: job_payload(jobs().get(job_id)))

    return server
