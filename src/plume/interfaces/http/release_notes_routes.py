"""Maintainer routes: release notes of a build and the post-release review (keep, roll back,
copy issues, promote/demote with a verified quote). Nothing here is public: suspect and unknown
items never leave the maintainer surfaces (docs/design/release-notes.md)."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from plume.application.knowledge.release_notes import QuoteNotVerifiedError, ReleaseNotes
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth


def release_notes_router(notes: Callable[[], ReleaseNotes], tokens: tuple[str, ...]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(make_auth(tokens))], tags=["maintainer"])
    errors: dict[int | str, dict[str, Any]] = {
        401: {"model": s.ErrorBody},
        404: {"model": s.ErrorBody},
        409: {"model": s.ErrorBody},
    }
    base = "/v1/apis/{api}/builds/{build}/release-notes"

    @router.get("/v1/apis/{api}/release-notes", responses=errors)
    def list_notes(api: str) -> dict[str, Any]:
        """Every build's notes summary of an API, newest first: review state, needsAttention,
        counts, and whether the build is `latest`."""
        return {"items": notes().summaries(api)}

    @router.get(base, responses=errors)
    def get_notes(api: str, build: str) -> dict[str, Any]:
        """All items (with suspect and unknown ones), the extraction report grouped by rule,
        the review and its decisions."""
        return notes().get(api, build)

    @router.post(f"{base}/keep", responses=errors)
    def keep(api: str, build: str, body: s.KeepRequest | None = None) -> dict[str, Any]:
        """Keep the build. On a rolled-back build this rolls it forward (latest back to it)
        while latest is still its base. 409 when already kept or latest moved on."""
        return notes().keep(api, build, body.note if body else None)

    @router.post(f"{base}/rollback", responses=errors)
    def rollback(api: str, build: str, body: s.RollbackRequest) -> dict[str, Any]:
        """Move `latest` from this build back to its base (the build stays loaded). 409 when
        the build is not `latest`, has no base, or is already rolled back."""
        return notes().rollback(api, build, body.reason)

    @router.get(f"{base}/issues", responses=errors)
    def issues(
        api: str,
        build: str,
        format: Annotated[str, Query(pattern="^(markdown|text)$")] = "markdown",
    ) -> PlainTextResponse:
        """The extraction report as one ready-to-paste text for stream (at most 200 items)."""
        media = "text/markdown" if format == "markdown" else "text/plain"
        return PlainTextResponse(notes().issues(api, build, format), media_type=media)

    @router.post(f"{base}/items/{{item_id}}/promote", responses={**errors, 422: {}})
    def promote(api: str, build: str, item_id: str, body: s.PromoteRequest) -> Any:
        """Confirm an item by hand with a quote verified against the new build's source.
        422 QUOTE_NOT_VERIFIED when the quote is not there."""
        try:
            return notes().promote(api, build, item_id, body.quote)
        except QuoteNotVerifiedError as exc:
            return JSONResponse(
                {"error": exc.code, "code": exc.code, "message": str(exc)}, status_code=422
            )

    @router.post(f"{base}/items/{{item_id}}/demote", responses=errors)
    def demote(api: str, build: str, item_id: str) -> dict[str, Any]:
        """Undo a promotion: the item goes back to its computed class."""
        return notes().demote(api, build, item_id)

    return router
