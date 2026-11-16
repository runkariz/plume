"""What newer docs mean for a saved model (release notes phase 3): instead of a blanket "stale",
which of the model's mappings cite something that changed (docs/design/release-notes.md
section 8). Only visible changes count (confirmed/likely); wording-only changes never affect a
mapping, and suspect extraction artifacts never do.

status:
- ``current``: every pinned build is still the API's latest;
- ``updated_unaffected``: newer builds exist and none of their visible changes touch a mapping;
- ``affected``: at least one mapping cites a changed field or endpoint;
- ``unknown``: a pinned build is not on the published chain of notes (older builds, or notes
  were not computed), so nothing is claimed.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from plume.application.knowledge.public_changes import PublicChanges, public_item
from plume.domain.knowledge.call_check import path_matches
from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import ModelSnapshot

RANK = {"current": 0, "updated_unaffected": 1, "unknown": 2, "affected": 3}
WIDGET_ROWS = 5


def _touches(item: dict[str, Any], docs: set[str], paths: set[str], fetch: str | None) -> bool:
    s = item["subject"]
    if fetch and s.get("method") and s.get("path") and not s.get("fieldPath"):
        method, _, path = fetch.partition(" ")
        if s["method"] == method.upper() and (
            s["path"] == path.strip() or path_matches(s["path"], path.strip())
        ):
            return True
    if s.get("docId") not in docs:
        return False
    field = s.get("fieldPath")
    if not field:  # the whole cited document changed (removed endpoint/model, scope ...)
        return True
    return any(p == field or p.startswith(f"{field}.") or field.startswith(f"{p}.") for p in paths)


class ModelImpact:
    def __init__(self, changes: PublicChanges) -> None:
        self._changes = changes

    def _newer(self, api: str, pinned: str) -> tuple[str | None, list[dict[str, Any]] | None]:
        """(latest build, the notes from latest back to pinned) or (latest, None) when pinned
        is not on the chain."""
        latest = self._changes.latest(api)
        if latest is None:
            return None, None
        if latest == pinned:  # still the published build: nothing newer, notes or not
            return latest, []
        chain = self._changes.chain(api)
        out = []
        for n in chain:
            out.append(n)
            if n["from"] == pinned:
                return latest, out
        return latest, None

    def of_model(self, snap: ModelSnapshot) -> dict[str, Any]:
        statuses: list[str] = []
        affected: list[dict[str, Any]] = []
        latest: dict[str, str | None] = {}
        for pin in snap.inputs:
            newest, notes = self._newer(pin.api, pin.build)
            latest[pin.api] = newest
            if newest is None:
                statuses.append("unknown")
                continue
            if notes is None:
                statuses.append("unknown")
                continue
            if not notes:
                statuses.append("current")
                continue
            items = [
                i
                for n in notes
                for i in n.get("items", [])
                if i.get("visibleToUsers") and not i.get("wordingOnly")
            ]
            hits = self._hits(snap, pin.api, items)
            affected += hits
            statuses.append("affected" if hits else "updated_unaffected")
        status = max(statuses, key=RANK.__getitem__) if statuses else "unknown"
        return {
            "status": status,
            "affectedCount": len(affected),
            "breakingCount": sum(1 for a in affected if a["change"]["breaking"]),
            "pinned": {p.api: p.build for p in snap.inputs},
            "latest": latest,
            "affected": affected,
        }

    def _hits(
        self, snap: ModelSnapshot, api: str, items: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, Any, Any, Any]] = set()
        for path, f in snap.draft.walk():
            for src_api, src in f.sources:
                if src_api != api:
                    continue
                docs = {e.doc_id for e in src.evidence}
                paths = {p.path.replace("[]", "") for p in src.paths} | {p.path for p in src.paths}
                for it in items:
                    if not _touches(it, docs, paths, src.fetch):
                        continue
                    s = it["subject"]
                    key = (path, s.get("docId"), s.get("fieldPath"), s.get("location"))
                    if key in seen:  # net effect: one row per mapping and changed subject
                        continue
                    seen.add(key)
                    out.append({"field": path, "api": api, "change": public_item(api, it)})
        return out

    def of_set(
        self, snap: ModelSetSnapshot, members: Iterable[tuple[str, ModelSnapshot]]
    ) -> dict[str, Any]:
        by_member = []
        affected: list[dict[str, Any]] = []
        for concept, model in members:
            m = self.of_model(model)
            by_member.append(
                {
                    "concept": concept,
                    "modelId": model.snapshot_id,
                    "status": m["status"],
                    "affectedCount": m["affectedCount"],
                }
            )
            affected += [{**a, "member": concept} for a in m["affected"]]
        status = (
            max((b["status"] for b in by_member), key=RANK.__getitem__) if by_member else "unknown"
        )
        return {
            "status": status,
            "affectedCount": len(affected),
            "breakingCount": sum(1 for a in affected if a["change"]["breaking"]),
            "byMember": by_member,
            "affected": affected,
        }


def summary(impact: dict[str, Any]) -> dict[str, Any]:
    """The small form for lists and model JSON."""
    return {k: impact[k] for k in ("status", "affectedCount", "breakingCount") if k in impact} | (
        {"byMember": impact["byMember"]} if "byMember" in impact else {}
    )


def widget_rows(impact: dict[str, Any]) -> list[dict[str, Any]]:
    """At most WIDGET_ROWS compact rows for the MCP view (no network there)."""
    rows = []
    for a in impact["affected"][:WIDGET_ROWS]:
        c = a["change"]
        what = c["subject"].get("fieldPath") or c["subject"].get("docId")
        reason = f" ({c['breakingReason']})" if c["breaking"] and c.get("breakingReason") else ""
        rows.append(
            {
                "field": a["field"],
                "api": a["api"],
                **({"member": a["member"]} if "member" in a else {}),
                "op": c["op"],
                "breaking": c["breaking"],
                "text": f"{c['kind'].replace('_', ' ')} {what} {c['op']}{reason}",
            }
        )
    return rows


def members_of(sets: Any, snap: ModelSetSnapshot) -> list[tuple[str, ModelSnapshot]]:
    """(concept, member model) pairs of a set (members that no longer exist are left out)."""
    return [(c, m) for c, m in sets.member_models(snap).items() if m is not None]
