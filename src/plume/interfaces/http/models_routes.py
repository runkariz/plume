"""Canonical-model routes. Reading is public; submitting a draft needs the maintainer token."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse

from plume.application.models.concepts import SuggestConcepts
from plume.application.models.sessions import ModelDraftRefusedError, ModelSessions
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.use_cases import ListApiOverviews
from plume.interfaces import payloads
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth


def _logo_for(logo: Callable[[str, str], dict[str, Any]], ref: dict[str, Any]) -> dict[str, Any]:
    return {**ref, "logo": logo(ref["id"], ref["name"])}


def models_router(
    suggest: Callable[[], SuggestConcepts],
    models: Callable[[], ModelSessions],
    resolver: Callable[[], BuildResolver],
    overviews: Callable[[], ListApiOverviews],
    summary: Callable[[Any], s.ApiSummary],
    logo: Callable[[str, str], dict[str, Any]],
    tokens: tuple[str, ...],
    claude_mcp_url: str,
) -> APIRouter:
    router = APIRouter(tags=["models"])
    auth = make_auth(tokens)
    errors: dict[int | str, dict[str, Any]] = {
        404: {"model": s.ErrorBody},
        400: {"model": s.ErrorBody},
    }

    def names(apis: list[str]) -> dict[str, str]:
        out = {}
        for a in apis:
            try:
                out[a] = resolver().resolve(a).api.name
            except Exception:
                out[a] = a
        return out

    def snapshot_json(snap: Any) -> dict[str, Any]:
        body = payloads.snapshot_payload(snap, names([i.api for i in snap.inputs]))
        body["inputs"] = [_logo_for(logo, i) for i in body["inputs"]]
        return body

    @router.get("/v1/models/candidates", response_model=s.ApiList, responses=errors)
    def candidates() -> s.ApiList:
        """APIs with a published build (the ones a model can be built from)."""
        return s.ApiList(items=[summary(o) for o in overviews().execute() if o.ref is not None])

    @router.post("/v1/models/suggest", response_model=s.SuggestResponse, responses=errors)
    def suggest_concepts(body: s.SuggestRequest) -> dict[str, Any]:
        out = payloads.suggestions_payload(suggest().execute(body.apis))
        out["apis"] = [_logo_for(logo, a) for a in out["apis"]]
        return out

    @router.post("/v1/models/generate", response_model=s.GenerateResponse, responses=errors)
    def generate(body: s.GenerateRequest) -> s.GenerateResponse:
        """Start a model session. Plume does not run an LLM: Claude writes the model through the
        maintainer MCP (or POST .../draft). If a snapshot already exists for the same concept on
        the current builds, its id is returned."""
        existing = models().existing(body.apis, body.concept)
        session = models().start(body.apis, body.concept)
        prompt = (
            f'Use the Plume maintainer MCP: get_model_context("{session.session_id}"), write the '
            f"canonical {body.concept} model for {', '.join(body.apis)}, then "
            f'submit_model_draft("{session.session_id}", draft).'
        )
        return s.GenerateResponse(
            session_id=session.session_id,
            status="ready" if existing else "awaiting_draft",
            snapshot_id=existing.snapshot_id if existing else None,
            inputs=[s.PinnedInput(api=i.api, build=i.build) for i in session.inputs],
            context_url=f"/v1/models/sessions/{session.session_id}/context",
            claude_prompt=prompt,
            mcp_url=claude_mcp_url,
            maintainer_mcp_url=claude_mcp_url.removesuffix("/mcp") + "/maintainer/mcp",
        )

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
        dependencies=[Depends(auth)],
        responses={**errors, 401: {"model": s.ErrorBody}, 422: {"model": s.DraftRefused}},
    )
    def submit(session_id: str, draft: Annotated[dict[str, Any], Body()]) -> JSONResponse:
        try:
            result = models().submit(session_id, draft)
        except ModelDraftRefusedError as exc:
            body = payloads.refusal_payload(exc.issues)
            return JSONResponse(
                {"error": exc.code, "message": str(exc), "detail": str(exc), **body},
                status_code=422,
            )
        return JSONResponse(
            {"created": result.created, "model": snapshot_json(result.snapshot)},
            status_code=201 if result.created else 200,
        )

    @router.get("/v1/models", response_model=s.ModelList, responses=errors)
    def list_models(
        api: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> s.ModelList:
        return s.ModelList(
            items=[
                s.ModelListItem(
                    id=m.snapshot_id,
                    name=m.draft.name,
                    concept=m.concept,
                    apis=[i.api for i in m.inputs],
                    generated_at=m.created_at.isoformat(),
                )
                for m in models().list(api, limit)
            ]
        )

    @router.get("/v1/models/{snapshot_id}", responses=errors)
    def get_model(snapshot_id: str) -> dict[str, Any]:
        """A model snapshot (ModelSnapshot in the web client)."""
        return snapshot_json(models().snapshot(snapshot_id))

    return router
