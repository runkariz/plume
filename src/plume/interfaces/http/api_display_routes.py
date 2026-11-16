"""Maintainer routes: an API's display name override; removing an API."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from plume.application.knowledge.api_display import ApiDisplayName
from plume.application.knowledge.remove_api import ApiInUseError, RemoveApi
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth


def api_display_router(
    display: Callable[[], ApiDisplayName],
    tokens: tuple[str, ...],
    remove: Callable[[], RemoveApi] | None = None,
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(make_auth(tokens))], tags=["maintainer"])
    errors: dict[int | str, dict[str, Any]] = {
        401: {"model": s.ErrorBody},
        404: {"model": s.ErrorBody},
        409: {"model": s.ErrorBody},
    }

    @router.put("/v1/apis/{api}/display", responses=errors)
    def set_display(api: str, body: s.DisplayNameIn) -> dict[str, Any]:
        """Set the API's display name (null clears it). Stored per API, not per build: it
        survives reloads and wins over the package's title and the derived name."""
        return display().set(api, body.name)

    if remove is not None:
        removal = remove

        @router.get("/v1/apis/{api}/removal", responses=errors)
        def removal_check(api: str) -> dict[str, Any]:
            """What removing the API would hit: the official/unreleased models and sets that
            pin its builds (removal is refused while any exist, unless forced)."""
            return {"api": api, "pinnedBy": removal().pinned_by(api)}

        @router.delete("/v1/apis/{api}", responses=errors)
        def remove_api(api: str, body: s.RemoveApiIn) -> Any:
            """Remove the API and everything it owns (builds, documents, tags, evals, release
            notes, package meta, jobs, display name) in one transaction, with an audit row.
            `confirm` must be the API id. 409 api_in_use (with `pinnedBy`) while official or
            unreleased models/sets pin its builds; `force: true` retires them first
            (official -> superseded, unreleased -> discarded)."""
            try:
                return removal().execute(api, body.confirm, body.force, body.reason)
            except ApiInUseError as exc:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": exc.code,
                        "message": str(exc),
                        "detail": str(exc),
                        "pinnedBy": exc.pinned,
                    },
                )

    return router
