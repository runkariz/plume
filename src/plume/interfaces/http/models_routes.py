"""Canonical-model routes.

Anyone (rate limited) can start a session, submit a draft (stored UNLISTED: readable by whoever
has its id, the share link), revise a model into a new version and list their own models with
owner keys. With the maintainer token: server-side generation (jobs + SSE), drafts stored
UNRELEASED, release / discard, and the unreleased lists. Public lists show official models only.
"""

import functools
import hmac
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from plume.application.models.concepts import SuggestFilter
from plume.application.models.generate import ENDED, GenerateModels
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import (
    ModelDraftRefusedError,
    ModelSessions,
    claude_prompt,
    normalize_concept,
)
from plume.application.ports.model_repo import ModelJob
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.use_cases import ListApiOverviews
from plume.domain.models.snapshot import ModelSnapshot, Origin, Visibility
from plume.interfaces import payloads
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import _sse, make_auth

WAIT_SECONDS = 15.0
KEEPALIVE_SECONDS = 15.0


def _logo_for(logo: Callable[[str, str], dict[str, Any]], ref: dict[str, Any]) -> dict[str, Any]:
    return {**ref, "logo": logo(ref["id"], ref["name"])}


def make_optional_auth(tokens: tuple[str, ...]) -> Callable[..., bool]:
    """True with a valid maintainer token, False without one; 401 for a wrong token."""

    def maintainer_or_anonymous(
        authorization: Annotated[str | None, Header()] = None,
    ) -> bool:
        if not authorization:
            return False
        scheme, _, token = authorization.partition(" ")
        ok = (
            scheme.lower() == "bearer"
            and bool(token)
            and any(hmac.compare_digest(token.encode(), t.encode()) for t in tokens)
        )
        if not ok:
            raise HTTPException(401, "invalid token", {"WWW-Authenticate": "Bearer"})
        return True

    return maintainer_or_anonymous


def job_out(job: ModelJob) -> s.ModelJobOut:
    return s.ModelJobOut(
        job_id=job.job_id,
        status=job.status,
        apis=list(job.apis),
        concept=job.concept,
        session_id=job.session_id,
        round=job.round,
        max_rounds=job.max_rounds,
        snapshot_id=None if _is_set(job) else job.snapshot_id,
        error=job.error,
        generator=job.generator,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        events_url=f"/v1/models/jobs/{job.job_id}/events",
        kind="model_set" if _is_set(job) else "model",
        set_id=job.snapshot_id if _is_set(job) else None,
        usage=job.usage,
    )


def _is_set(job: ModelJob) -> bool:
    return (job.session_id or "").startswith("ss-")


def models_router(  # noqa: PLR0915
    suggest: Callable[[], Any],
    models: Callable[[], ModelSessions],
    resolver: Callable[[], BuildResolver],
    overviews: Callable[[], ListApiOverviews],
    summary: Callable[[Any], s.ApiSummary],
    logo: Callable[[str, str], dict[str, Any]],
    tokens: tuple[str, ...],
    claude_mcp_url: str,
    generate_models: Callable[[], GenerateModels] | None = None,
    web_public_url: str | None = None,
    suggest_related: Callable[[], SuggestRelated] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["models"])
    auth = make_auth(tokens)
    optional = make_optional_auth(tokens)
    errors: dict[int | str, dict[str, Any]] = {
        404: {"model": s.ErrorBody},
        400: {"model": s.ErrorBody},
        429: {"model": s.ErrorBody},
    }
    token_errors: dict[int | str, dict[str, Any]] = {**errors, 401: {"model": s.ErrorBody}}
    maintainer_mcp_url = claude_mcp_url.removesuffix("/mcp") + "/maintainer/mcp"

    def names(apis: list[str]) -> dict[str, str]:
        out = {}
        for a in apis:
            try:
                out[a] = resolver().resolve(a).api.name
            except Exception:
                out[a] = a
        return out

    def snapshot_json(snap: ModelSnapshot, maintainer: bool) -> dict[str, Any]:
        service = models()
        body = payloads.snapshot_payload(
            snap, names([i.api for i in snap.inputs]), service.stale_inputs(snap)
        )
        body["inputs"] = [_logo_for(logo, i) for i in body["inputs"]]
        body.update(
            payloads.access_payload(snap, service.lineage_info(snap, maintainer), web_public_url)
        )
        body["supersedes"] = list(service.replaced_by(snap))
        return body

    def list_item(m: ModelSnapshot, maintainer: bool) -> s.ModelListItem:
        service = models()
        stale = service.stale_inputs(m)
        return s.ModelListItem(
            id=m.snapshot_id,
            name=m.draft.name,
            concept=normalize_concept(m.concept),
            apis=[i.api for i in m.inputs],
            generated_at=m.created_at.isoformat(),
            stale=bool(stale),
            stale_inputs=[
                s.StaleInput(api=str(x["api"]), pinned=str(x["pinned"]), current=x["current"])
                for x in stale
            ],
            visibility=m.visibility,
            official=m.visibility == Visibility.OFFICIAL,
            version=m.version,
            versions=service.lineage_info(m, maintainer)["versions"],
            lineage_id=m.lineage,
            same_concept=list(service.same_concept(m))
            if m.visibility == Visibility.OFFICIAL
            else [],
        )

    def generator() -> GenerateModels:
        if generate_models is None:
            raise HTTPException(503, "server-side generation is not configured")
        return generate_models()

    @router.get("/v1/models/candidates", response_model=s.ApiList, responses=errors)
    def candidates() -> s.ApiList:
        """APIs with a published build (the ones a model can be built from)."""
        return s.ApiList(items=[summary(o) for o in overviews().execute() if o.ref is not None])

    @router.post("/v1/models/suggest", response_model=s.SuggestResponse, responses=errors)
    def suggest_concepts(body: s.SuggestRequest) -> dict[str, Any]:
        """Concepts the selected APIs document, best first, paged and filtered (see the request
        fields). Deterministic: no LLM."""
        f = SuggestFilter(
            q=body.q,
            only=body.only,
            require=tuple(body.require),
            in_all=body.in_all,
            write_only=body.write_only,
            limit=body.limit,
            offset=body.offset,
        )
        out = payloads.suggestions_payload(suggest().execute(body.apis, f))
        out["apis"] = [_logo_for(logo, a) for a in out["apis"]]
        return out

    if suggest_related is not None:
        related = suggest_related

        @router.post("/v1/models/suggest-related", responses=errors)
        def suggest_related_concepts(body: s.SuggestRelatedRequest) -> dict[str, Any]:
            """Concepts related to one concept in these APIs, with relation candidates taken
            only from documented evidence (nested arrays, sub-resources, id fields whose
            description names the target, model references), each cited per API, and the
            designs that evidence supports. Different names (variant / variation) appear only as
            `aliases` for the user to accept. Deterministic: no LLM."""
            out = payloads.related_payload(
                related().execute(body.apis, body.concept, body.limit, body.offset)
            )
            out["apis"] = [_logo_for(logo, a) for a in out["apis"]]
            return out

    @router.post(
        "/v1/models/generate",
        response_model=s.GenerateResponse,
        responses={
            **token_errors,
            202: {"model": s.ModelJobOut},
            503: {"model": s.ErrorBody},
        },
    )
    def generate(body: s.GenerateRequest, maintainer: Annotated[bool, Depends(optional)]) -> Any:
        """engine=claude (default without the token): start a session your Claude fills; the
        model is stored unlisted (unreleased with the token). engine=server (maintainer token;
        default with it): Plume generates the model with its LLM → 202 with the job; the model
        is stored unreleased. `ready` returns an existing model only when the caller may see it
        (official; unreleased too for a maintainer)."""
        engine = body.engine or ("server" if maintainer else "claude")
        if engine == "server" and not maintainer:
            raise HTTPException(401, "server generation needs the maintainer token")
        service = models()
        existing = service.existing(body.apis, body.concept, maintainer)
        if engine == "server" and not (existing and not body.force):
            job = generator().start(body.apis, body.concept)
            return JSONResponse(
                job_out(job).model_dump(by_alias=True, mode="json"), status_code=202
            )
        session = service.start(
            body.apis, body.concept, Origin.MAINTAINER if maintainer else Origin.USER
        )
        return s.GenerateResponse(
            session_id=session.session_id,
            status="ready" if existing else "awaiting_draft",
            snapshot_id=existing.snapshot_id if existing else None,
            inputs=[s.PinnedInput(api=i.api, build=i.build) for i in session.inputs],
            context_url=f"/v1/models/sessions/{session.session_id}/context",
            claude_prompt=claude_prompt(session, maintainer),
            mcp_url=claude_mcp_url,
            maintainer_mcp_url=maintainer_mcp_url,
        )

    @router.get(
        "/v1/models/jobs/{job_id}",
        response_model=s.ModelJobOut,
        dependencies=[Depends(auth)],
        responses=token_errors,
    )
    def get_job(job_id: str) -> s.ModelJobOut:
        """A server-side generation job (maintainer)."""
        return job_out(generator().get(job_id))

    @router.get(
        "/v1/models/jobs/{job_id}/events",
        dependencies=[Depends(auth)],
        responses={**token_errors, 200: {"content": {"text/event-stream": {}}}},
        response_class=StreamingResponse,
    )
    async def job_events(
        job_id: str,
        request: Request,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events; `event:` = queued|started|context|round|refused|accepted|failed|
        done. Resume with the Last-Event-ID header. The stream ends after `done`."""
        service = generator()
        await anyio.to_thread.run_sync(lambda: service.get(job_id))  # 404 before streaming
        try:
            start = int(last_event_id) if last_event_id else 0
        except ValueError:
            start = 0

        async def stream() -> AsyncIterator[str]:
            seq = start
            idle = 0.0
            while True:
                batch = await anyio.to_thread.run_sync(
                    functools.partial(service.events_after, job_id, seq)
                )
                for n, payload in batch:
                    seq = n
                    yield _sse(n, payload)
                    if payload.get("type") == "done":
                        return
                if batch:
                    idle = 0.0
                    continue
                job = await anyio.to_thread.run_sync(functools.partial(service.get, job_id))
                if job.status in ENDED or await request.is_disconnected():
                    return
                woke = await anyio.to_thread.run_sync(
                    functools.partial(service.wait_events, job_id, seq, WAIT_SECONDS)
                )
                idle = 0.0 if woke else idle + WAIT_SECONDS
                if idle >= KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get(
        "/v1/models/sessions/{session_id}", response_model=s.SessionStatus, responses=errors
    )
    def session_status(session_id: str) -> s.SessionStatus:
        """For pollers: `submitted` with the snapshot id once a draft was accepted."""
        return s.SessionStatus(**models().session_status(session_id))

    @router.get("/v1/models/sessions/{session_id}/context", responses=errors)
    def context(session_id: str) -> dict[str, Any]:
        """Index of the session's evidence (documents per API with field counts)."""
        return models().context(session_id)

    @router.get("/v1/models/sessions/{session_id}/evidence", responses=errors)
    def evidence(
        session_id: str,
        api: Annotated[str, Query()],
        doc: Annotated[list[str] | None, Query()] = None,
        cursor: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        """Fields of the concept's documents in one API (or of `doc` ids), paged by size."""
        return models().evidence(session_id, api, doc, cursor)

    @router.post(
        "/v1/models/sessions/{session_id}/draft",
        status_code=201,
        responses={**token_errors, 422: {"model": s.DraftRefused}},
    )
    def submit(
        session_id: str,
        draft: Annotated[dict[str, Any], Body()],
        maintainer: Annotated[bool, Depends(optional)],
        based_on: Annotated[str | None, Query(alias="basedOn")] = None,
    ) -> JSONResponse:
        """Validate and store a draft: unlisted without the token (the response carries the
        model's link and, for a new model, its `ownerKey`, shown once), unreleased with it.
        `basedOn` makes it the next version of that model when you may add to it."""
        try:
            result = models().submit(session_id, draft, based_on, maintainer)
        except ModelDraftRefusedError as exc:
            body = payloads.refusal_payload(exc.issues)
            return JSONResponse(
                {"error": exc.code, "message": str(exc), "detail": str(exc), **body},
                status_code=422,
            )
        snap = result.snapshot
        return JSONResponse(
            {
                "created": result.created,
                "visibility": snap.visibility,
                "ownerKey": result.owner_key,
                "model": snapshot_json(snap, maintainer),
            },
            status_code=201 if result.created else 200,
        )

    @router.post("/v1/models/mine", response_model=s.ModelList, responses=errors)
    def mine(body: s.MineRequest) -> s.ModelList:
        """The latest version of each model started with one of these owner keys (POST so the
        keys stay out of URLs and logs)."""
        return s.ModelList(items=[list_item(m, False) for m in models().mine(body.owner_keys)])

    @router.get("/v1/models", response_model=s.ModelList, responses=token_errors)
    def list_models(
        maintainer: Annotated[bool, Depends(optional)],
        api: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        visibility: Annotated[
            str, Query(pattern="^(official|unreleased|superseded|all)$")
        ] = "official",
    ) -> s.ModelList:
        """Official models (the latest released version of each). With the maintainer token,
        `visibility=unreleased|superseded|all` lists the others too. Newest first."""
        if visibility != "official" and not maintainer:
            raise HTTPException(401, "this list needs the maintainer token")
        wanted = {
            "official": (Visibility.OFFICIAL,),
            "unreleased": (Visibility.UNRELEASED,),
            "superseded": (Visibility.SUPERSEDED,),
            "all": Visibility.ALL,
        }[visibility]
        return s.ModelList(
            items=[list_item(m, maintainer) for m in models().list(api, limit, wanted)]
        )

    @router.get("/v1/models/{snapshot_id}", responses=token_errors)
    def get_model(
        snapshot_id: str, maintainer: Annotated[bool, Depends(optional)]
    ) -> dict[str, Any]:
        """A model (ModelSnapshot in the web client): official and unlisted ones for anyone with
        the id; unreleased ones with the maintainer token (404 otherwise)."""
        return snapshot_json(models().visible_snapshot(snapshot_id, maintainer), maintainer)

    @router.post(
        "/v1/models/{snapshot_id}/revise", response_model=s.RevisedSession, responses=errors
    )
    def revise(
        snapshot_id: str, maintainer: Annotated[bool, Depends(optional)]
    ) -> s.RevisedSession:
        """A session on the current builds with this model as the starting draft. Submit with
        basedOn to make a new version (an official model revised without the token becomes a new
        unlisted model based on it)."""
        r = models().revise(snapshot_id, maintainer)
        return s.RevisedSession(
            session_id=r["session_id"],
            based_on=r["based_on"],
            concept=r["concept"],
            inputs=[s.PinnedInput(**i) for i in r["inputs"]],
            starting_draft=r["starting_draft"],
            claude_prompt=r["claude_prompt"],
            context_url=f"/v1/models/sessions/{r['session_id']}/context",
        )

    @router.post(
        "/v1/models/{snapshot_id}/release",
        dependencies=[Depends(auth)],
        responses={**token_errors, 409: {"model": s.ErrorBody}},
    )
    def release(snapshot_id: str, body: s.ReleaseRequest | None = None) -> dict[str, Any]:
        """Make an unreleased model official (listed publicly). 409 unless it is unreleased.
        ``supersedes``: official models of the same concept (from /supersedable) that this one
        replaces: they stay readable by id with supersededBy, and leave the lists. 409 when an
        id is not one of them."""
        wanted = body.supersedes if body else []
        out = snapshot_json(models().release(snapshot_id, wanted), True)
        out["supersedes"] = list(dict.fromkeys(wanted))
        return out

    @router.post(
        "/v1/models/{snapshot_id}/supersede",
        dependencies=[Depends(auth)],
        responses={**token_errors, 400: {"model": s.ErrorBody}, 409: {"model": s.ErrorBody}},
    )
    def supersede(snapshot_id: str, body: s.ReleaseRequest) -> dict[str, Any]:
        """An official model retires older official models of its concept (ids from
        /supersedable): they stay readable by id with supersededBy and leave the lists. 409
        when this model is not official or an id is not a candidate; nothing changes then."""
        out = snapshot_json(models().supersede(snapshot_id, body.supersedes), True)
        out["supersedes"] = list(dict.fromkeys(body.supersedes))
        return out

    @router.get(
        "/v1/models/{snapshot_id}/supersedable",
        dependencies=[Depends(auth)],
        responses={**token_errors, 404: {"model": s.ErrorBody}},
    )
    def supersedable(snapshot_id: str) -> dict[str, Any]:
        """Official models of the same concept (case-insensitive) over ANY API set that a
        release of this model may supersede, newest first. covered: its APIs are a subset of
        this model's. Offer them; nothing is superseded unless release names it."""
        service = models()
        return {"items": service.supersedable(service.snapshot(snapshot_id))}

    @router.post(
        "/v1/models/{snapshot_id}/discard",
        dependencies=[Depends(auth)],
        responses={**token_errors, 409: {"model": s.ErrorBody}},
    )
    def discard(snapshot_id: str) -> dict[str, Any]:
        """Throw away an unreleased model. 409 unless it is unreleased."""
        return snapshot_json(models().discard(snapshot_id), True)

    return router
