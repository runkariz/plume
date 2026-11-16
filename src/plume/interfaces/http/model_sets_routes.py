"""Model set routes (docs/design/model-relations.md): several canonical models with relations.

Same access rules as models: anyone (rate limited) can start a set session and save an UNLISTED
set (the id is the share link, an owner key lists it); with the maintainer token a set is stored
UNRELEASED, and release makes it official together with its unreleased members.
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from plume.application.models.generate import GenerateModels
from plume.application.models.impact import ModelImpact, members_of
from plume.application.models.impact import summary as impact_summary
from plume.application.models.model_sets import ModelSets
from plume.application.models.sessions import ModelDraftRefusedError
from plume.application.reader.resolve import BuildResolver
from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import Visibility
from plume.interfaces import payloads
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth
from plume.interfaces.http.models_routes import job_out, make_optional_auth


def model_sets_router(  # noqa: PLR0915 - one route per operation
    sets: Callable[[], ModelSets],
    resolver: Callable[[], BuildResolver],
    logo: Callable[[str, str], dict[str, Any]],
    tokens: tuple[str, ...],
    web_public_url: str | None = None,
    generate_models: Callable[[], GenerateModels] | None = None,
    impact: Callable[[], ModelImpact] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["model sets"])
    auth = make_auth(tokens)
    optional = make_optional_auth(tokens)
    errors: dict[int | str, dict[str, Any]] = {
        400: {"model": s.ErrorBody},
        401: {"model": s.ErrorBody},
        404: {"model": s.ErrorBody},
        409: {"model": s.ErrorBody},
        429: {"model": s.ErrorBody},
    }

    def names(apis: list[str]) -> dict[str, str]:
        out = {}
        for a in apis:
            try:
                out[a] = resolver().resolve(a).api.display_name
            except Exception:
                out[a] = a
        return out

    def item(service: ModelSets, x: ModelSetSnapshot, maintainer: bool) -> dict[str, Any]:
        out = payloads.set_list_item(
            x, service.stale_inputs(x), service.lineage_info(x, maintainer)["versions"]
        )
        if impact is not None:
            out["impact"] = impact_summary(impact().of_set(x, members_of(service, x)))
        return out

    def set_json(x: ModelSetSnapshot, maintainer: bool) -> dict[str, Any]:
        service = sets()
        body = payloads.set_payload(
            x,
            service.member_models(x),
            service.lineage_info(x, maintainer),
            service.stale_inputs(x),
            names([i.api for i in x.inputs]),
            web_public_url,
        )
        body["inputs"] = [{**i, "logo": logo(i["id"], i["name"])} for i in body["inputs"]]
        if impact is not None:
            body["impact"] = impact_summary(impact().of_set(x, members_of(service, x)))
        editable = service.editable_options(x)
        for rel in body["relations"]:
            rel["editableOptions"] = editable.get(rel["id"], [])
        return body

    @router.post("/v1/model-sets/sessions", responses=errors)
    def start(
        body: s.SetSessionRequest, maintainer: Annotated[bool, Depends(optional)]
    ) -> dict[str, Any]:
        """Pin the builds of 2..6 APIs once for 1..8 concepts: one model session per member."""
        aliases = [a.model_dump() for a in body.aliases]
        x = sets().start(
            body.apis, body.concepts, "maintainer" if maintainer else "user", aliases=aliases
        )
        alias_text = "".join(
            f" Treat {' and '.join(f'{api} {n!r}' for api, n in names)} as {c}; record it under "
            "aliases."
            for c, names in x.aliases
        )
        return {
            "setSessionId": x.session_id,
            "inputs": [{"api": i.api, "build": i.build} for i in x.inputs],
            "memberSessions": dict(x.member_sessions),
            "contextUrl": f"/v1/model-sets/sessions/{x.session_id}/context",
            "claudePrompt": (
                f'Use the Plume MCP: get_set_context("{x.session_id}"), write or reuse a model for '
                f"each of {', '.join(x.concepts)}, ask me how each relation should be designed, "
                f'then submit_model_set("{x.session_id}", draft).' + alias_text
            ),
            "aliases": x.aliases_json(),
        }

    @router.post(
        "/v1/model-sets/generate",
        status_code=202,
        dependencies=[Depends(auth)],
        response_model=s.ModelJobOut,
        responses={**errors, 503: {"model": s.ErrorBody}},
    )
    def generate(body: s.SetSessionRequest) -> s.ModelJobOut:
        """Maintainer: Plume writes every member model with its LLM (same validation), then
        proposes relations from the documented candidates as UNDECIDED (confirmed: false).
        The set is stored unreleased; decide the relations, then release. Progress:
        GET /v1/models/jobs/{jobId} and its events (kind model_set, setId)."""
        if generate_models is None:
            raise HTTPException(503, "server-side generation is not configured")
        aliases = [a.model_dump() for a in body.aliases]
        return job_out(generate_models().start_set(sets(), body.apis, body.concepts, aliases))

    @router.get("/v1/model-sets/sessions/{session_id}", responses=errors)
    def session_status(session_id: str) -> dict[str, Any]:
        return sets().session_status(session_id)

    @router.get("/v1/model-sets/sessions/{session_id}/context", responses=errors)
    def context(session_id: str, maintainer: Annotated[bool, Depends(optional)]) -> dict[str, Any]:
        """Members (evidence index + reusable models) and relation candidates with evidence."""
        return sets().context(session_id, maintainer)

    @router.post("/v1/model-sets/sessions/{session_id}/draft", status_code=201, responses=errors)
    def submit(
        session_id: str,
        draft: Annotated[dict[str, Any], Body()],
        maintainer: Annotated[bool, Depends(optional)],
        based_on: Annotated[str | None, Query(alias="basedOn")] = None,
        collection: Annotated[str | None, Query(max_length=100)] = None,
    ) -> JSONResponse:
        """Validate and store a set: unlisted without the token, saved into the user's "My
        models" link (`collection`; a new one when omitted or unknown, returned as
        `collection`), unreleased with it. Relations the user has not decided carry
        confirmed:false."""
        try:
            result = sets().submit(session_id, draft, based_on, maintainer, collection=collection)
        except ModelDraftRefusedError as exc:
            body = payloads.refusal_payload(exc.issues)
            return JSONResponse(
                {"error": exc.code, "message": str(exc), "detail": str(exc), **body},
                status_code=422,
            )
        x = result.snapshot
        return JSONResponse(
            {
                "created": result.created,
                "visibility": x.visibility,
                "collection": payloads.collection_payload(result.collection, web_public_url),
                "set": set_json(x, maintainer),
            },
            status_code=201 if result.created else 200,
        )

    @router.post("/v1/model-sets/mine", responses=errors)
    def mine(body: s.MineRequest) -> dict[str, Any]:
        service = sets()
        return {"items": [item(service, x, False) for x in service.mine(body.owner_keys)]}

    @router.get("/v1/model-sets", responses=errors)
    def list_sets(
        maintainer: Annotated[bool, Depends(optional)],
        api: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        visibility: Annotated[str, Query(pattern="^(official|unreleased|all)$")] = "official",
    ) -> dict[str, Any]:
        """Official sets (latest released version of each); with the token
        `visibility=unreleased|all`. Newest first."""
        if visibility != "official" and not maintainer:
            raise HTTPException(401, "this list needs the maintainer token")
        wanted = {
            "official": (Visibility.OFFICIAL,),
            "unreleased": (Visibility.UNRELEASED,),
            "all": Visibility.ALL,
        }[visibility]
        service = sets()
        return {"items": [item(service, x, maintainer) for x in service.list(api, limit, wanted)]}

    if impact is not None:
        impacts = impact

        @router.get("/v1/model-sets/{set_id}/impact", responses=errors)
        def set_impact(
            set_id: str, maintainer: Annotated[bool, Depends(optional)]
        ) -> dict[str, Any]:
            """What newer docs mean for the set: per member, its affected mappings."""
            service = sets()
            x = service.visible(set_id, maintainer)
            return impacts().of_set(x, members_of(service, x))

    @router.get("/v1/model-sets/{set_id}", responses=errors)
    def get_set(set_id: str, maintainer: Annotated[bool, Depends(optional)]) -> dict[str, Any]:
        """A set: members (each a model, GET /v1/models/{modelId}), relations with per-API
        evidence, lineage and link. Unreleased sets need the token (404 otherwise)."""
        return set_json(sets().visible(set_id, maintainer), maintainer)

    @router.post("/v1/model-sets/{set_id}/revise", responses=errors)
    def revise(set_id: str, maintainer: Annotated[bool, Depends(optional)]) -> dict[str, Any]:
        r = sets().revise(set_id, maintainer)
        return {
            "setSessionId": r["set_session_id"],
            "basedOn": r["based_on"],
            "memberSessions": r["member_sessions"],
            "startingDraft": r["starting_draft"],
            "membersCurrent": r["members_current"],
            "next": r["next"],
        }

    @router.post("/v1/model-sets/{set_id}/relations", status_code=201, responses=errors)
    def edit_relations(
        set_id: str,
        body: s.RelationEditRequest,
        maintainer: Annotated[bool, Depends(optional)],
        collection: Annotated[str | None, Query(max_length=100)] = None,
    ) -> JSONResponse:
        """The web's relation editor: change relation designs (kind, cardinality, embed/ref,
        confirmed) of the latest version; a new version is stored (unlisted without the token,
        unreleased with it). Only designs whose fields exist in the members pass (see each
        relation's `editableOptions`); anything else is a revision with Claude (422)."""
        try:
            result = sets().edit_relations(set_id, body.relations, maintainer, collection)
        except ModelDraftRefusedError as exc:
            out = payloads.refusal_payload(exc.issues)
            return JSONResponse(
                {"error": exc.code, "message": str(exc), "detail": str(exc), **out},
                status_code=422,
            )
        x = result.snapshot
        return JSONResponse(
            {
                "created": result.created,
                "visibility": x.visibility,
                "collection": payloads.collection_payload(result.collection, web_public_url),
                "set": set_json(x, maintainer),
            },
            status_code=201 if result.created else 200,
        )

    @router.post("/v1/model-sets/{set_id}/release", dependencies=[Depends(auth)], responses=errors)
    def release(set_id: str) -> dict[str, Any]:
        """Make an unreleased set official AND release its unreleased members (listed in
        `releasedMembers`). 409 while a relation is undecided."""
        r = sets().release(set_id)
        return {"set": set_json(r.snapshot, True), "releasedMembers": list(r.released_members)}

    @router.post("/v1/model-sets/{set_id}/discard", dependencies=[Depends(auth)], responses=errors)
    def discard(set_id: str) -> dict[str, Any]:
        return set_json(sets().discard(set_id), True)

    return router
