"""The HTTP API. Reader routes are public (rate limited); they call the same use cases as MCP."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from plume import __version__
from plume.application.errors import (
    ApplicationError,
    GateFailedError,
    NotFoundError,
    SourcePackageError,
)
from plume.application.jobs.maintainer import JobStateError, MaintainerJobs
from plume.application.knowledge.api_display import ApiDisplayName
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.knowledge.public_changes import PublicChanges
from plume.application.knowledge.release_notes import ReleaseNotes
from plume.application.knowledge.remove_api import RemoveApi
from plume.application.models.collections import Collections
from plume.application.models.concepts import ModelInputError, SuggestConcepts
from plume.application.models.generate import GenerateModels
from plume.application.models.impact import ModelImpact
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import ModelSessions
from plume.application.ports.model_writer import ModelWriterError, ModelWriterUnavailableError
from plume.application.reader import links
from plume.application.reader.dto import ApiOverview
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.sections import PackageSections
from plume.application.reader.use_cases import (
    BrowseDocuments,
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    ReaderInputError,
    SearchDocs,
)
from plume.domain.eval.metrics import few_questions_note
from plume.domain.knowledge import rate_limits
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.errors import DomainError, InvalidIdentifierError
from plume.domain.shared.ids import BuildId
from plume.interfaces import payloads
from plume.interfaces.http import schemas as s
from plume.interfaces.http.api_display_routes import api_display_router
from plume.interfaces.http.changes_routes import changes_router
from plume.interfaces.http.maintainer import is_maintainer, maintainer_router
from plume.interfaces.http.model_sets_routes import model_sets_router
from plume.interfaces.http.models_routes import models_router
from plume.interfaces.http.rate_limit import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from plume.interfaces.http.release_notes_routes import release_notes_router
from plume.interfaces.http.sections_routes import sections_router

ApiPath = Annotated[str, Path(description="API id, e.g. shopify")]
Version = Annotated[str | None, Query(description="Tag or build id; default latest")]
_PALETTE = ("#5b5bd6", "#0d9488", "#d97706", "#db2777", "#2563eb", "#65a30d", "#7c3aed", "#dc2626")


@dataclass(frozen=True, slots=True)
class HttpDependencies:
    overviews: Callable[[], ListApiOverviews]
    browse: Callable[[], BrowseDocuments]
    search: Callable[[], SearchDocs]
    get_document: Callable[[], GetDocument]
    find_fact: Callable[[], FindFact]
    check_call: Callable[[], CheckCall]
    list_builds: Callable[[], ListBuilds]
    diff_builds: Callable[[], DiffBuilds]
    resolver: Callable[[], BuildResolver]
    sections: Callable[[], PackageSections] | None = None
    mcp_url: str = "http://127.0.0.1:18481/mcp"
    rate_limit_per_minute: int = 120
    trusted_proxy_hops: int = 0
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:18473", "http://localhost:18473")
    maintainer: Callable[[], MaintainerJobs] | None = None
    suggest: Callable[[], SuggestConcepts] | None = None
    models: Callable[[], ModelSessions] | None = None
    maintainer_tokens: tuple[str, ...] = ()
    max_upload_bytes: int = 200 * 1024 * 1024
    generate_models: Callable[[], GenerateModels] | None = None
    suggest_related: Callable[[], SuggestRelated] | None = None
    model_sets: Callable[[], ModelSets] | None = None
    web_public_url: str | None = None
    collections: Callable[[], Collections] | None = None
    release_notes: Callable[[], ReleaseNotes] | None = None
    public_changes: Callable[[], PublicChanges] | None = None
    api_display: Callable[[], ApiDisplayName] | None = None
    remove_api: Callable[[], RemoveApi] | None = None
    model_impact: Callable[[], ModelImpact] | None = None


MAX_RAW_BYTES = 256 * 1024


def _list_of_dicts(raw: Any, key: str) -> list[dict[str, Any]]:
    value = raw.get(key) if isinstance(raw, dict) else None
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _generation_flag(
    generate: Callable[[], GenerateModels] | None,
) -> Callable[[], bool] | None:
    """Whether server-side generation is configured (for GET /v1/maintainer/me)."""
    if generate is None:
        return None
    return lambda: generate().available()


def _logo(api_id: str, name: str, icon_url: str | None) -> s.Logo:
    return s.Logo(**payloads.letter_logo(api_id, name, icon_url))


def _summary(o: ApiOverview) -> s.ApiSummary:
    info = o.info
    return s.ApiSummary(
        id=info.api_id.value,
        name=info.display_name,
        name_source=info.display_source,
        category=info.category.key if info.category else "other",
        summary=info.summary,
        endpoints=o.counts.get("endpoint", 0),
        models=o.counts.get("model", 0),
        model_shapes=o.counts.get("model_shapes", 0),
        model_names=o.counts.get("model_names", 0),
        guides=o.counts.get("guide", 0),
        docs_as_of=o.ref.docs_as_of if o.ref else None,
        status=s.ApiStatus(
            kind="ready" if o.ref else "unpublished",
            recall_at5=o.eval.metrics.recall_at_k if o.eval else None,
        ),
        # Only the package's own icon, served by Plume; never a remote URL.
        logo=_logo(
            info.api_id.value,
            info.display_name,
            f"/v1/apis/{info.api_id.value}/icon" if o.has_icon else None,
        ),
    )


def _citation(c: payloads.Json) -> s.Citation:
    return s.Citation(**c)


def create_app(deps: HttpDependencies) -> FastAPI:
    app = FastAPI(
        title="Plume API",
        version=__version__,
        description="Reader API over sealed builds of API documentation. Every response names "
        "the build it was read from. Retrieval only: clients (Claude) write the answers.",
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=deps.max_upload_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=deps.rate_limit_per_minute,
        trusted_proxy_hops=deps.trusted_proxy_hops,
        trusted_tokens=deps.maintainer_tokens,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(deps.cors_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "Accept"],
        expose_headers=["Content-Disposition", "Retry-After"],
    )

    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            {"error": code, "message": message, "detail": message}, status_code=status
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            401: "unauthorized",
            413: "too_large",
            415: "unsupported_media_type",
            503: "unavailable",
        }
        r = error(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail))
        for k, v in (exc.headers or {}).items():
            r.headers[k] = v
        return r

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return error(404, exc.code, str(exc))

    @app.exception_handler(ReaderInputError)
    async def bad_input(_: Request, exc: ReaderInputError) -> JSONResponse:
        return error(400, exc.code, str(exc))

    @app.exception_handler(SourcePackageError)
    async def bad_package(_: Request, exc: SourcePackageError) -> JSONResponse:
        return error(400, exc.code, str(exc))

    @app.exception_handler(GateFailedError)
    async def gate_failed(_: Request, exc: GateFailedError) -> JSONResponse:
        return error(409, exc.code, str(exc))

    @app.exception_handler(JobStateError)
    async def job_state(_: Request, exc: JobStateError) -> JSONResponse:
        return error(409, exc.code, str(exc))

    @app.exception_handler(ModelInputError)
    async def model_input(_: Request, exc: ModelInputError) -> JSONResponse:
        return error(400, exc.code, str(exc))

    @app.exception_handler(ModelWriterUnavailableError)
    async def llm_unavailable(_: Request, exc: ModelWriterUnavailableError) -> JSONResponse:
        return error(503, exc.code, str(exc))

    @app.exception_handler(ModelWriterError)
    async def llm_failed(_: Request, exc: ModelWriterError) -> JSONResponse:
        return error(502, exc.code, str(exc))

    @app.exception_handler(ApplicationError)
    async def app_error(_: Request, exc: ApplicationError) -> JSONResponse:
        return error(409, exc.code, str(exc))

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return error(400, "invalid_input", str(exc))

    responses: dict[int | str, dict[str, object]] = {
        404: {"model": s.ErrorBody},
        400: {"model": s.ErrorBody},
        429: {"model": s.ErrorBody},
    }

    def _section_counts(api: str, version: str | None) -> s.SectionCounts | None:
        if deps.sections is None:
            return None
        c = deps.sections().counts(api, version)
        return s.SectionCounts(
            auth=c.auth, triggers=c.triggers, webhook_endpoints=c.webhook_endpoints
        )

    @app.get("/health", response_model=s.Health, tags=["system"])
    def health() -> s.Health:
        return s.Health(status="ok", version=__version__)

    @app.get("/v1/apis", response_model=s.ApiList, tags=["reader"], responses=responses)
    def list_apis() -> s.ApiList:
        return s.ApiList(items=[_with_docs(_summary(o)) for o in deps.overviews().execute()])

    def _with_docs(summary: s.ApiSummary) -> s.ApiSummary:
        if deps.public_changes is None:
            return summary
        updated = deps.public_changes().docs_updated(summary.id)
        return summary.model_copy(
            update={"docs_updated": s.DocsUpdated(**updated) if updated else None}
        )

    @app.get("/v1/apis/{api}", response_model=s.ApiDetail, tags=["reader"], responses=responses)
    def get_api(
        api: ApiPath,
        version: Version = None,
        authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
    ) -> Response:
        """One API. packageWarnings only for a maintainer bearer token (absent otherwise);
        notices are public."""
        maintainer = is_maintainer(authorization, deps.maintainer_tokens)
        detail = _api_detail(api, version, maintainer)
        body = detail.model_dump(
            mode="json", by_alias=True, exclude=None if maintainer else {"package_warnings"}
        )
        headers = {"Vary": "Authorization"}  # the body depends on the token
        if maintainer:
            headers["Cache-Control"] = "private, no-store"
        return JSONResponse(body, headers=headers)

    def _api_detail(api: str, version: str | None, maintainer: bool) -> s.ApiDetail:
        o = deps.overviews().one(api, version)
        base = _with_docs(_summary(o))
        if o.ref is None:  # pragma: no cover - one() always resolves a build
            raise NotFoundError(f"{api} has no published build")
        return s.ApiDetail(
            **base.model_dump(),
            chunks=o.counts.get("chunks", 0),
            is_live=o.ref.tag is not None,
            tag=o.ref.tag,
            tags=list(o.tags),
            versions=list(o.info.versions),
            doc_link=o.info.doc_link,
            quality=(
                s.Quality(
                    recall_at5=o.eval.metrics.recall_at_k,
                    mrr=o.eval.metrics.mrr,
                    top1_rate=o.eval.metrics.top1_rate,
                    fact_accuracy=o.eval.metrics.fact_accuracy,
                    missing_expected=o.eval.metrics.missing_expected,
                    gold_questions=o.eval.metrics.questions,
                    note=few_questions_note(o.eval.metrics.questions),
                    gate_passed=o.eval.passed,
                    evaluated_at=o.eval.evaluated_at.isoformat(),
                    by_source=[
                        s.SourceQuality(
                            source=name,
                            recall_at5=m.recall_at_k,
                            mrr=m.mrr,
                            top1_rate=m.top1_rate,
                            questions=m.search_questions,
                        )
                        for name, m in o.eval.metrics.by_source
                    ],
                )
                if o.eval
                else None
            ),
            index=s.IndexInfo(
                embedding=o.embed_model,
                dimensions=o.dims,
                store="postgres+pgvector (halfvec, hnsw) + tsvector",
                build=o.ref.build,
            ),
            connect=s.Connect(
                claude_code=f"claude mcp add --transport http plume {deps.mcp_url}",
                mcp_url=deps.mcp_url,
            ),
            sections=_section_counts(api, version),
            rate_limits=deps.sections().rate_limits(api, version) if deps.sections else [],
            **_warnings(api, version, maintainer),
            **_sources(o.ref.build),
        )

    def _warnings(api: str, version: str | None, maintainer: bool) -> dict[str, Any]:
        """Notices for everyone; the package's own warnings only for a maintainer."""
        if deps.sections is None:
            return {"package_warnings": [] if maintainer else None}
        sections = deps.sections()
        found = sections.package_warnings(api, version) if maintainer else []
        return {
            "package_warnings": (
                [s.PackageWarningOut(code=w.code, text=w.text) for w in found]
                if maintainer
                else None
            ),
            "notices": [s.Notice(**n) for n in sections.notices(api, None, version)],
        }

    def _sources(build: str) -> dict[str, Any]:
        info = deps.release_notes().public_sources(build) if deps.release_notes else None
        if info is None:
            return {}
        return {
            "sources": [
                s.SourceRef(url=x["url"], kind=x["kind"], fetched_at=x["fetchedAt"])
                for x in info["sources"]
            ],
            "extracted_at": info["extractedAt"],
        }

    @app.get(
        "/v1/apis/{api}/items", response_model=s.BrowseResult, tags=["reader"], responses=responses
    )
    def browse(
        api: ApiPath,
        kind: s.KindFilter = "all",
        tag: Annotated[str | None, Query(max_length=100, description="Package tag")] = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        version: Version = None,
    ) -> s.BrowseResult:
        ref, items, total = deps.browse().execute(api, kind, q, limit, offset, version, tag)
        return s.BrowseResult(
            build=ref.build,
            items=[
                s.BrowseItem(
                    id=i.doc_id,
                    kind=i.kind.value,
                    title=i.title,
                    method=i.method,
                    path=i.path,
                    real_path=i.real_path,
                    resource=i.resource,
                    deprecated=i.deprecated,
                    tags=list(i.tags),
                )
                for i in items
            ],
            total=total,
        )

    @app.get(
        "/v1/apis/{api}/documents/{doc_id:path}",
        response_model=s.DocumentOut,
        tags=["reader"],
        responses=responses,
    )
    def get_document(api: ApiPath, doc_id: str, version: Version = None) -> s.DocumentOut:
        r = deps.get_document().execute(api, doc_id, version)
        d = r.document
        raw_too_big = d.raw is not None and len(json.dumps(d.raw)) > MAX_RAW_BYTES
        return s.DocumentOut(
            api=r.ref.api,
            build=r.ref.build,
            docs_as_of=r.ref.docs_as_of,
            id=d.doc_id,
            kind=d.kind.value,
            title=d.title,
            resource=d.resource,
            method=d.method,
            path=d.path,
            real_path=d.real_path,
            version_fixed=d.real_path is not None,
            rate_limit=rate_limits.as_dict(d.rate_limit),
            deprecated=d.deprecated,
            complete=d.complete,
            source_url=d.source_url,
            anchor=d.anchor,
            text=d.text,
            fields=[
                s.FieldOut(
                    name=f.name,
                    location=f.location.value,
                    type=f.type,
                    required=f.required,
                    description=f.description,
                    constraints=f.constraint_dict or None,
                )
                for f in d.fields
            ],
            scopes=list(d.scopes),
            required_scopes=links.required_scopes(d),
            guides=links.linked_guides(d),
            linked_endpoints=links.linked_endpoints(d),
            endpoint_links=[
                s.EndpointLink(endpoint_id=e["endpointId"], link_basis=e["linkBasis"])
                for e in links.endpoint_links(d)
            ],
            tags=list(d.tags),
            responses=_list_of_dicts(d.raw, "responses") if d.kind.value == "endpoint" else [],
            errors=_list_of_dicts(d.raw, "errors") if d.kind.value == "endpoint" else [],
            raw=None if raw_too_big else (dict(d.raw) if d.raw is not None else None),
            raw_truncated=raw_too_big,
        )

    @app.post(
        "/v1/apis/{api}/search",
        response_model=s.SearchResponse,
        tags=["reader"],
        responses=responses,
    )
    def search(api: ApiPath, body: s.SearchRequest) -> s.SearchResponse:
        r = deps.search().execute(api, body.query, body.mode, body.kind, body.top_k, body.version)
        return s.SearchResponse(
            api=r.ref.api,
            build=r.ref.build,
            docs_as_of=r.ref.docs_as_of,
            results=[
                s.SearchHit(
                    id=h.doc_id,
                    kind=h.kind.value,
                    title=h.title,
                    subtitle=h.subtitle,
                    snippet=h.snippet,
                    source_url=h.source_url,
                    dense_rank=h.dense_rank,
                    text_rank=h.text_rank,
                    dense_score=h.dense_score,
                    text_score=h.text_score,
                    fused=h.fused,
                )
                for h in r.hits
            ],
            trace=[s.TraceStep(source=t.source, label=t.label, ms=t.ms) for t in r.trace],
            total_ms=r.total_ms,
            claude_payload=json.dumps(payloads.search_payload(r), indent=2, ensure_ascii=False),
        )

    @app.post(
        "/v1/apis/{api}/ask", response_model=s.AskResponse, tags=["reader"], responses=responses
    )
    def ask(api: ApiPath, body: s.AskRequest) -> s.AskResponse:
        r = deps.search().execute(api, body.question, "hybrid", None, body.top_k, body.version)
        return s.AskResponse(
            api=r.ref.api,
            build=r.ref.build,
            docs_as_of=r.ref.docs_as_of,
            question=body.question,
            passages=[
                s.Passage(id=h.doc_id, title=h.title, quote=h.snippet, source_url=h.source_url)
                for h in r.hits
            ],
            trace=[s.TraceStep(source=t.source, label=t.label, ms=t.ms) for t in r.trace],
            total_ms=r.total_ms,
        )

    @app.post(
        "/v1/apis/{api}/check-call",
        response_model=s.CheckCallResponse,
        tags=["reader"],
        responses=responses,
    )
    def check_call(api: ApiPath, body: s.CheckCallRequest) -> s.CheckCallResponse:
        r = deps.check_call().execute(api, body.method, body.path, body.params, body.version)
        p = payloads.check_call_payload(r)
        return s.CheckCallResponse(
            api=r.ref.api,
            build=r.ref.build,
            verdict=p["verdict"],
            complete=r.complete,
            matched=(
                s.MatchedEndpoint(
                    id=r.matched_id,
                    method=r.matched_method or "",
                    path=r.matched_path or "",
                    real_path=r.matched_real_path,
                )
                if r.matched_id
                else None
            ),
            param_checks=[
                s.ParamCheck(name=c.name, found=c.found, where=c.where) for c in r.params
            ],
            checked=s.Checked(**r.checked),
            evidence=_citation(p["evidence"]) if p["evidence"] else None,
            alternatives=list(r.alternatives),
        )

    @app.post(
        "/v1/apis/{api}/find-fact",
        response_model=s.FindFactResponse,
        tags=["reader"],
        responses=responses,
    )
    def find_fact(api: ApiPath, body: s.FindFactRequest) -> s.FindFactResponse:
        r = deps.find_fact().execute(
            api,
            body.name,
            kind=body.kind,
            owner=body.owner,
            resource=body.resource,
            location=body.location,
            version=body.version,
        )
        p = payloads.find_fact_payload(r)
        return s.FindFactResponse(
            api=r.ref.api,
            build=r.ref.build,
            docs_as_of=r.ref.docs_as_of,
            name=r.name,
            found=r.found,
            complete=r.complete,
            checked=s.Checked(**r.checked),
            matches=[
                s.FactMatch(**{**m, "evidence": _citation(m["evidence"])}) for m in p["matches"]
            ],
            incomplete_sources=list(r.incomplete_sources),
            incomplete_reasons=list(r.reasons),
            text_mentions=[
                s.SearchHit(
                    id=h.doc_id,
                    kind=h.kind.value,
                    title=h.title,
                    subtitle=h.subtitle,
                    snippet=h.snippet,
                    source_url=h.source_url,
                    dense_rank=None,
                    text_rank=h.text_rank,
                    dense_score=0.0,
                    text_score=0.0,
                    fused=0.0,
                )
                for h in r.text_mentions
            ],
            wording=r.wording,
        )

    @app.get(
        "/v1/apis/{api}/builds", response_model=s.BuildList, tags=["builds"], responses=responses
    )
    def builds(api: ApiPath) -> s.BuildList:
        try:
            api_id = ApiId(api)
        except InvalidIdentifierError as exc:
            raise NotFoundError(f"unknown api {api!r}") from exc
        views = deps.list_builds().execute(api_id)
        if not views:
            deps.resolver().resolve(api)  # 404 for an unknown api
        return s.BuildList(
            api=api,
            items=[
                s.BuildOut(
                    id=v.build.build_id.value,
                    status=v.build.status.value,
                    created_at=v.build.created_at.isoformat(),
                    sealed_at=v.build.sealed_at.isoformat() if v.build.sealed_at else None,
                    items=len(v.build),
                    content_hash=v.build.content_hash.value if v.build.content_hash else None,
                    tags=list(v.tags),
                    embed_model=v.build.spec.embed_model if v.build.spec else None,
                    package_hash=v.build.spec.package_hash if v.build.spec else None,
                )
                for v in views
            ],
        )

    @app.get("/v1/apis/{api}/diff", response_model=s.DiffOut, tags=["builds"], responses=responses)
    def diff(
        api: ApiPath,
        from_build: Annotated[str, Query(alias="from")],
        to_build: Annotated[str, Query(alias="to")],
    ) -> s.DiffOut:
        old = deps.resolver().resolve(api, from_build).build
        new = deps.resolver().resolve(api, to_build).build
        d = deps.diff_builds().execute(BuildId(old.build_id.value), new.build_id)
        return s.DiffOut(
            api=api,
            from_build=old.build_id.value,
            to_build=new.build_id.value,
            added=list(d.added),
            changed=list(d.changed),
            removed=list(d.removed),
            unchanged=d.unchanged,
        )

    if deps.sections is not None:
        app.include_router(sections_router(deps.sections))

    def _icon_url(api: str) -> str | None:
        """The package icon's path when the API's latest build has one (else the letter tile)."""
        if deps.sections is None:
            return None
        try:
            return f"/v1/apis/{api}/icon" if deps.sections().has_icon(api) else None
        except ApplicationError:
            return None

    if deps.suggest is not None and deps.models is not None:
        app.include_router(
            models_router(
                deps.suggest,
                deps.models,
                deps.resolver,
                deps.overviews,
                _summary,
                lambda api, name: _logo(api, name, _icon_url(api)).model_dump(by_alias=True),
                deps.maintainer_tokens,
                deps.mcp_url,
                deps.generate_models,
                deps.web_public_url,
                deps.suggest_related,
                deps.model_sets,
                deps.collections,
                deps.model_impact,
            )
        )
    if deps.model_sets is not None:
        app.include_router(
            model_sets_router(
                deps.model_sets,
                deps.resolver,
                lambda api, name: _logo(api, name, _icon_url(api)).model_dump(by_alias=True),
                deps.maintainer_tokens,
                deps.web_public_url,
                deps.generate_models,
                deps.model_impact,
            )
        )
    if deps.release_notes is not None:
        app.include_router(release_notes_router(deps.release_notes, deps.maintainer_tokens))
    if deps.api_display is not None:
        app.include_router(
            api_display_router(deps.api_display, deps.maintainer_tokens, deps.remove_api)
        )
    if deps.public_changes is not None:
        app.include_router(
            changes_router(
                deps.public_changes,
                lambda: [o.info.api_id.value for o in deps.overviews().execute() if o.ref],
            )
        )
    if deps.maintainer is not None:
        app.include_router(
            maintainer_router(
                deps.maintainer,
                deps.maintainer_tokens,
                deps.max_upload_bytes,
                _generation_flag(deps.generate_models),
            )
        )
    return app
