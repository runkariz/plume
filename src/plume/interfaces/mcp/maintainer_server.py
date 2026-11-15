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
from plume.application.models.concepts import SuggestConcepts, SuggestFilter
from plume.application.models.generate import GenerateModels
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import ModelSessions
from plume.application.reader.resolve import BuildResolver
from plume.domain.shared.ids import BuildId
from plume.interfaces import payloads
from plume.interfaces.mcp.apps.model_view import (
    MODEL_ONLY_META,
    model_view_apps,
    model_view_html,
)
from plume.interfaces.mcp.model_tools import register_model_tools
from plume.interfaces.mcp.reader_server import _run
from plume.interfaces.mcp.set_tools import register_set_tools

INSTRUCTIONS = """\
Plume maintainer tools. Canonical models across 2..N APIs:
1. suggest_concepts(apis) to see which concepts the APIs share (coverage per API).
2. start_model_session(apis, concept) pins the latest build of each API.
3. get_model_context(model_session) returns a compact index (per API the concept's documents
   with field counts), the draft format and the rules. Then get_model_evidence(model_session,
   api) per API returns the fields with descriptions, page by page (follow next_cursor; pass
   doc_ids to read other documents of the pinned build).
4. Write the model, then submit_model_draft(model_session, draft). Plume checks every citation
   (document exists, quote is in it, field and endpoint exist). A refusal lists issue codes;
   fix and resubmit. An accepted draft becomes an immutable UNRELEASED snapshot: review it
   (get_model) and release_model(id) to make it official, or discard_model(id).
5. Or let Plume write it: generate_model(apis, concept) runs its LLM with the same validation
   and returns a job; get_generation(job_id) until succeeded, then review and release.
6. Changing a model: revise_model(id) then submit_model_draft(..., based_on=id) = a new
   (unreleased) version of the same model; list_models(visibility="unreleased") to review.
Before reusing a stored model (list_models / get_model), check stale: true means a pinned
build is no longer latest; regenerate it with a new session or ask.
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
    generate: Callable[[], GenerateModels] | None = None
    web_public_url: str | None = None
    suggest_related: Callable[[], SuggestRelated] | None = None
    model_sets: Callable[[], ModelSets] | None = None
    mcp_app_html: str | None = None


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
        extensions=[model_view_apps(deps.mcp_app_html or model_view_html())],
    )

    @server.tool(annotations=READ, structured_output=True)
    async def suggest_concepts(
        apis: list[str],
        q: str | None = None,
        only: str = "multi",
        require: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Concepts the APIs document (deterministic), best first: coverage per API, a factual
        reason and counts. only = multi (in 2+ APIs) | single | all; q filters by text;
        require = API ids where the concept must exist. Follow nextOffset for more."""
        f = SuggestFilter(q=q, only=only, require=tuple(require or ()), limit=limit, offset=offset)
        return await _run(lambda: payloads.suggestions_payload(deps.suggest().execute(apis, f)))

    register_model_tools(
        server,
        deps.models,
        deps.resolver,
        _run,
        True,
        deps.web_public_url,
        deps.generate,
        deps.suggest_related,
    )
    if deps.model_sets is not None:
        register_set_tools(
            server,
            deps.model_sets,
            deps.resolver,
            _run,
            True,
            deps.web_public_url,
            deps.generate,
        )

    @server.tool(annotations=WRITE, structured_output=True, meta=MODEL_ONLY_META)
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
