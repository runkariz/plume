"""Public release notes (phase 3): what changed in an API's docs, along its published builds.
Only confirmed and likely changes; never the extraction report (maintainers only)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from plume.application.knowledge.public_changes import PublicChanges
from plume.interfaces.http import schemas as s

ATOM = "application/atom+xml; charset=utf-8"


def _line(i: dict[str, Any]) -> str:
    what = i["subject"].get("fieldPath") or i["subject"].get("docId")
    out = f"- {i['kind'].replace('_', ' ')} {what} {i['op']}"
    if i["breaking"]:
        out += " (BREAKING)"
    if i["perVendorChangelog"]:
        out += " [per the vendor's changelog]"
    if i.get("vendorUrl"):
        out += f" {i['vendorUrl']}"
    return out


def _atom_entry(api: str, base: str, n: dict[str, Any]) -> str:
    c = n["counts"]
    title = f"{api}: {c['confirmed'] + c['likely']} change(s)" + (
        f", {c['breaking']} BREAKING" if c["breaking"] else ""
    )
    lines = "\n".join(_line(i) for i in n["items"])
    return (
        "<entry>"
        f"<id>urn:plume:{escape(api)}:{escape(n['build'])}</id>"
        f"<title>{escape(title)}</title>"
        f"<updated>{escape(n['docsAsOf'])}T00:00:00Z</updated>"
        f'<link href="{escape(base)}/v1/apis/{escape(api)}/changes?build={escape(n["build"])}"/>'
        f'<content type="text">{escape(lines)}</content>'
        "</entry>"
    )


def _feed(title: str, feed_id: str, entries: list[str]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<id>{escape(feed_id)}</id><title>{escape(title)}</title><updated>{now}</updated>"
        + "".join(entries)
        + "</feed>"
    )


def changes_router(
    changes: Callable[[], PublicChanges], apis: Callable[[], list[str]]
) -> APIRouter:
    router = APIRouter(tags=["reader"])
    errors: dict[int | str, dict[str, Any]] = {
        400: {"model": s.ErrorBody},
        404: {"model": s.ErrorBody},
    }

    def entries(api: str, base: str, limit: int = 20) -> list[str]:
        service = changes()
        out = []
        for t in service.timeline(api)[:limit]:
            if t["counts"]["confirmed"] + t["counts"]["likely"] == 0:
                continue
            page = service.changes(api, build=t["build"], limit=200)
            out.append(_atom_entry(api, base, {**t, "items": page["items"]}))
        return out

    @router.get("/v1/apis/{api}/changes/timeline", responses=errors)
    def timeline(api: str) -> dict[str, Any]:
        """The published builds with release notes, newest first (latest, then its base, …),
        with their visible counts. Builds that were rolled back are not on it."""
        return {"api": api, "items": changes().timeline(api)}

    @router.get("/v1/apis/{api}/changes", responses=errors)
    def list_changes(
        api: str,
        build: Annotated[str | None, Query()] = None,
        since: Annotated[str | None, Query(description="A date (YYYY-MM-DD) or a build id")] = None,
        breaking: Annotated[bool | None, Query()] = None,
        kind: Annotated[
            str | None, Query(max_length=200, description="A kind or a comma list of kinds")
        ] = None,
        op: Annotated[str | None, Query(max_length=20)] = None,
        wording_only: Annotated[bool | None, Query(alias="wordingOnly")] = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, Any]:
        """Confirmed and likely changes of the latest build (or `build`, or every published
        build `since` a date/build), breaking first. `totals` count the whole selection."""
        return changes().changes(
            api, build, since, breaking=breaking, kind=kind, op=op, wording_only=wording_only,
            q=q, cursor=cursor, limit=limit,
        )  # fmt: skip

    @router.get("/v1/apis/{api}/changes.atom", responses=errors)
    def atom(api: str, request: Request) -> Response:
        """Atom feed of the API's published changes (one entry per build)."""
        base = str(request.base_url).rstrip("/")
        body = _feed(f"Plume: {api} docs changes", f"urn:plume:{api}", entries(api, base))
        return Response(body, media_type=ATOM)

    @router.get("/v1/changes.atom")
    def atom_all(request: Request) -> Response:
        """Atom feed of every API's published changes."""
        base = str(request.base_url).rstrip("/")
        items: list[str] = []
        for api in apis():
            items += entries(api, base, 5)
        return Response(_feed("Plume: docs changes", "urn:plume:all", items), media_type=ATOM)

    return router
