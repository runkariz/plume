"""Release notes for everyone (phase 3, docs/design/release-notes.md section 8): only
`confirmed` and `likely` items, along the chain of the TAGGED build (latest -> its base -> ...).
Suspect and unknown items are never shown or counted here, and a rolled-back build is not on
the public chain."""

from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

from plume.application.errors import ApplicationError
from plume.application.ports.release_notes_repo import ReleaseNotesRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import LATEST, TagName

MAX_LIMIT = 200
MAX_CHAIN = 100  # builds walked back from latest
_KIND_ORDER = ("endpoint", "param", "request_field", "response_field", "model", "property",
               "auth_scheme", "scope", "environment", "versioning", "webhook_event",
               "guide")  # fmt: skip


class ChangesInputError(ApplicationError):
    code = "invalid_input"


def _http(url: str | None) -> str | None:
    return url if url and url.startswith(("https://", "http://")) else None


def public_item(api: str, item: dict[str, Any]) -> dict[str, Any]:
    """What the public sees of one visible item (no artifact rules, hashes or review data)."""
    ev = item.get("evidence") or {}
    subject = item["subject"]
    removed_doc = item["op"] == "removed" and not subject.get("fieldPath")
    return {
        "id": item["id"],
        "from": item["from"],
        "to": item["to"],
        "toDocsAsOf": item["toDocsAsOf"],
        "kind": item["kind"],
        "op": item["op"],
        "subject": subject,
        "before": item.get("before"),
        "after": item.get("after"),
        "breaking": item["breaking"],
        "breakingReason": item.get("breakingReason"),
        "class": item["class"],
        "perVendorChangelog": item["class"] == "likely",
        "wordingOnly": item["wordingOnly"],
        "quote": ev.get("quote"),
        "vendorUrl": _http(ev.get("sourceUrl")),
        "anchor": ev.get("anchor"),
        "sourceKind": ev.get("sourceKind"),
        # a removed endpoint/model/... is still readable in the build it was removed from
        "documentUrl": (
            f"/v1/apis/{api}/documents/{subject['docId']}?version={item['from']}"
            if item["op"] == "removed"
            else f"/v1/apis/{api}/documents/{subject['docId']}?version={item['to']}"
        )
        if subject.get("docId")
        else None,
        "removedDocument": removed_doc,
    }


def change_text(i: dict[str, Any]) -> str:
    """One plain line: "DELETE /orders/{id} removed", "param status (GET /orders) required",
    "property currency removed"."""
    s = i["subject"]
    kind = i["kind"].replace("_", " ")
    where = f"{s['method']} {s['path']}" if s.get("method") and s.get("path") else None
    if s.get("fieldPath"):
        what = s["fieldPath"] + (f" ({where})" if where else "")
    elif where:  # a whole endpoint: METHOD path
        return f"{where} {i['op']}"
    else:
        what = s.get("model") or s.get("docId") or ""
    return f"{kind} {what} {i['op']}"


def _visible(notes: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in notes.get("items", []) if i.get("visibleToUsers")]


def _counts(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "confirmed": sum(1 for i in items if i["class"] == "confirmed"),
        "likely": sum(1 for i in items if i["class"] == "likely"),
        "breaking": sum(1 for i in items if i["breaking"]),
        "wordingOnly": sum(1 for i in items if i["wordingOnly"]),
        "byKind": dict(sorted(Counter(i["kind"] for i in items).items())),
    }


def _order(i: dict[str, Any]) -> tuple[Any, ...]:
    kind = _KIND_ORDER.index(i["kind"]) if i["kind"] in _KIND_ORDER else len(_KIND_ORDER)
    s = i["subject"]
    return (not i["breaking"], kind, s.get("docId") or "", s.get("fieldPath") or "", i["op"])


class PublicChanges:
    def __init__(self, notes: ReleaseNotesRepo, tags: TagRepo) -> None:
        self._notes = notes
        self._tags = tags

    def latest(self, api: str) -> str | None:
        tag = self._tags.get(ApiId(api), TagName(LATEST))
        return tag.build_id.value if tag else None

    def chain(self, api: str) -> list[dict[str, Any]]:
        """The notes along the public chain: latest, then its base, and so on (newest first).
        Stops at the first build without notes."""
        tag = self._tags.get(ApiId(api), TagName(LATEST))
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        build = tag.build_id.value if tag else None
        while build and build not in seen and len(out) < MAX_CHAIN:
            seen.add(build)
            notes = self._notes.get(build)
            if notes is None or notes.get("api") != api:
                break
            out.append(notes)
            build = notes.get("from")
        return out

    def docs_updated(self, api: str) -> dict[str, Any] | None:
        """For API cards: the latest build's visible changes (wording-only excluded), or None
        when it has none (or no notes). Only the latest build's notes are read (the chain's
        first link), never the chain."""
        tag = self._tags.get(ApiId(api), TagName(LATEST))
        notes = self._notes.get(tag.build_id.value) if tag else None
        return _docs_updated(api, notes)

    def docs_updated_many(self, latest: dict[str, str]) -> dict[str, dict[str, Any] | None]:
        """docs_updated for many APIs ({api: its latest build}) in one read of their notes."""
        notes = self._notes.card_notes(list(latest.values()))
        return {api: _docs_updated(api, notes.get(build)) for api, build in latest.items()}

    def timeline(self, api: str) -> list[dict[str, Any]]:
        latest = self._tags.get(ApiId(api), TagName(LATEST))
        out = []
        for n in self.chain(api):
            c = _counts(_visible(n))
            out.append(
                {
                    "build": n["to"],
                    "from": n["from"],
                    "docsAsOf": n["toDocsAsOf"],
                    "latest": latest is not None and latest.build_id.value == n["to"],
                    "counts": {k: c[k] for k in ("confirmed", "likely", "breaking", "wordingOnly")},
                }
            )
        return out

    def _select(self, api: str, build: str | None, since: str | None) -> list[dict[str, Any]]:
        chain = self.chain(api)
        if build and since:
            raise ChangesInputError("pass build or since, not both")
        if build:
            picked = [n for n in chain if n["to"] == build]
            if not picked:
                raise ChangesInputError(f"build {build} is not on {api}'s published chain")
            return picked
        if since:
            ids = [n["to"] for n in chain]
            if since in ids:  # a build: everything after it
                return chain[: ids.index(since)]
            try:
                day = date.fromisoformat(since)
            except ValueError as exc:
                raise ChangesInputError("since is a date (YYYY-MM-DD) or a build id") from exc
            return [n for n in chain if date.fromisoformat(n["toDocsAsOf"]) >= day]
        return chain[:1]

    def changes(
        self,
        api: str,
        build: str | None = None,
        since: str | None = None,
        *,
        breaking: bool | None = None,
        kind: str | None = None,
        op: str | None = None,
        wording_only: bool | None = None,
        q: str | None = None,
        cursor: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        notes = self._select(api, build, since)
        items = [i for n in notes for i in _visible(n)]
        if breaking is not None:
            items = [i for i in items if i["breaking"] == breaking]
        if kind:  # one kind or a comma list (kind=param,property)
            kinds = {k.strip() for k in kind.split(",") if k.strip()}
            items = [i for i in items if i["kind"] in kinds]
        if op:
            items = [i for i in items if i["op"] == op]
        if wording_only is not None:
            items = [i for i in items if i["wordingOnly"] == wording_only]
        totals = _counts(items)  # the whole selection, before q and paging
        if q:
            needle = q.lower()
            items = [
                i
                for i in items
                if needle
                in " ".join(
                    str(i["subject"].get(k) or "") for k in ("docId", "fieldPath", "path", "model")
                ).lower()
            ]
        items.sort(key=_order)
        cursor, limit = max(0, cursor), max(1, min(limit, MAX_LIMIT))
        page = items[cursor : cursor + limit]
        return {
            "api": api,
            "builds": [n["to"] for n in notes],
            "computedAt": max((n["computedAt"] for n in notes), default=None),
            "totals": totals,
            "matched": len(items),
            "items": [public_item(api, i) for i in page],
            "nextCursor": cursor + limit if cursor + limit < len(items) else None,
        }


def _docs_updated(api: str, latest: dict[str, Any] | None) -> dict[str, Any] | None:
    """The latest build's visible changes for an API card (wording-only excluded), or None:
    no notes, notes of another API (as the chain stops), or nothing visible."""
    if latest is None or latest.get("api") != api:
        return None
    items = [i for i in _visible(latest) if not i["wordingOnly"]]
    if not items:
        return None
    c = _counts(items)
    return {
        "build": latest["to"],
        "at": latest["toDocsAsOf"],
        "confirmed": c["confirmed"],
        "likely": c["likely"],
        "breaking": c["breaking"],
    }
