"""Maintainer route: an API's display name override."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from plume.application.knowledge.api_display import ApiDisplayName
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth


def api_display_router(display: Callable[[], ApiDisplayName], tokens: tuple[str, ...]) -> APIRouter:
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

    return router
