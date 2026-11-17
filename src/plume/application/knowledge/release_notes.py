"""Use cases: release notes between builds of one API, and the maintainer's post-release review
(docs/design/release-notes.md). Nothing here blocks a publish: the notes are computed before
the tag moves, the review comes after (keep, roll back, promote with a verified quote)."""

import copy
from dataclasses import replace
from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.release_notes_repo import ReleaseNotesRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.release_notes import (
    CONFIRMED,
    Item,
    PackageMeta,
    attention,
    classify,
    counts,
    diff_documents,
    docs_updated,
    finish,
    in_text,
    issues_text,
    page_texts,
    report,
)
from plume.domain.knowledge.tag import LATEST, Tag, TagName
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

MAX_REASON = 500
REPORT_PAGE = 50
PENDING, KEPT, ROLLED_BACK = "pending", "kept", "rolled_back"


class ReleaseStateError(ApplicationError):
    code = "invalid_state"


class QuoteNotVerifiedError(ApplicationError):
    code = "QUOTE_NOT_VERIFIED"


class ReleaseNotes:
    def __init__(
        self,
        builds: BuildRepo,
        documents: DocumentRepo,
        tags: TagRepo,
        notes: ReleaseNotesRepo,
        clock: Clock,
        evals: EvalRepo | None = None,
        max_drop: float = 0.05,
    ) -> None:
        self._builds = builds
        self._documents = documents
        self._tags = tags
        self._notes = notes
        self._clock = clock
        self._evals = evals
        self._max_drop = max_drop
        self._texts: dict[str, dict[str, str]] = {}  # build -> source snapshots (load only)

    # -- computing --------------------------------------------------------------------------------

    def record_meta(self, build_id: BuildId, meta: PackageMeta) -> None:
        """Keep what the package said about its extraction (the next build's notes use it)."""
        self._notes.save_meta(build_id.value, meta.as_json())
        if meta.page_texts:
            self._texts[build_id.value] = dict(meta.page_texts)

    def _meta(self, build_id: str) -> PackageMeta:
        meta = PackageMeta.from_json(self._notes.get_meta(build_id))
        texts = self._texts.get(build_id)
        if texts:
            meta = replace(meta, page_texts=texts)
        return meta

    def _gold(self, a: BuildId, b: BuildId) -> dict[str, Any] | None:
        if self._evals is None:
            return None
        ra, rb = self._evals.get(a), self._evals.get(b)
        if ra is None or rb is None:
            return None
        keep = ("recall_at_k", "mrr", "fact_accuracy", "citation_hit_rate")
        return {
            side: {k: v for k, v in r.metrics.as_dict().items() if k in keep}
            for side, r in (("before", ra), ("after", rb))
        }

    def compute(self, from_build: BuildId, to_build: BuildId) -> dict[str, Any]:
        """The notes of ``to_build`` against ``from_build`` (both of one API). A recomputation
        keeps the review, the decisions and promotions of items that still exist."""
        a, b = require_build(self._builds, from_build), require_build(self._builds, to_build)
        if a.api_id != b.api_id:
            raise ApplicationError(f"builds belong to different APIs ({a.api_id}, {b.api_id})")
        old = self._documents.list_documents(from_build)
        new = self._documents.list_documents(to_build)
        meta_a, meta_b = self._meta(from_build.value), self._meta(to_build.value)
        previous = self._notes.get(from_build.value)
        items = diff_documents(old, new)
        classify(items, old, new, meta_a, meta_b, (previous or {}).get("items", ()))
        docs_as_of = (b.sealed_at or b.created_at).date().isoformat()
        finish(items, b.api_id.value, from_build.value, to_build.value, docs_as_of)
        prior = self._notes.get(to_build.value)
        review, decisions = PENDING, []
        if prior is not None and prior.get("from") == from_build.value:
            review, decisions = prior.get("review", PENDING), prior.get("decisions", [])
            promoted = {i["id"]: i for i in prior.get("items", []) if i.get("promotedAt")}
            for it in items:
                if it["id"] in promoted:
                    p = promoted[it["id"]]
                    it.update(
                        {
                            "class": CONFIRMED,
                            "visibleToUsers": True,
                            "promotedBy": p["promotedBy"],
                            "promotedAt": p["promotedAt"],
                            "evidence": {**it["evidence"], "quote": p["evidence"]["quote"]},
                        }
                    )
        gold = self._gold(from_build, to_build)
        reason = attention(items, gold, self._max_drop)
        notes: dict[str, Any] = {
            "api": b.api_id.value,
            "from": from_build.value,
            "to": to_build.value,
            "toDocsAsOf": docs_as_of,
            "computedAt": self._clock.now().isoformat(),
            "review": review,
            "decisions": decisions,
            "package": {"from": meta_a.as_json(), "to": meta_b.as_json()},
            "extractorChanged": (meta_a.stream_version, meta_a.rules_hash)
            != (meta_b.stream_version, meta_b.rules_hash)
            and meta_a.rules_hash is not None,
            "gold": gold,
            "counts": counts(items),
            "docsUpdated": docs_updated(old, new),
            "needsAttention": reason is not None,
            "attentionReason": reason,
            # maintainers only: stream's conflicts between sources, and which units it compared
            "conflicts": [dict(c) for c in meta_b.conflicts],
            "conflictCheck": {
                "checked": len(meta_b.conflicts_checked),
                "notCompared": len(meta_b.conflicts_unchecked),
            },
            "items": items,
        }
        self._notes.save(notes)
        return notes

    def on_load(
        self, api_id: ApiId, build_id: BuildId, meta: PackageMeta | None
    ) -> dict[str, Any] | None:
        """After a load, before the tag moves: compare with the build ``latest`` points to."""
        if meta is not None:
            self.record_meta(build_id, meta)
        base = self._tags.get(api_id, TagName(LATEST))
        if base is None or base.build_id == build_id:
            return None
        return self.compute(base.build_id, build_id)

    def public_sources(self, build_id: str) -> dict[str, Any] | None:
        """What the public may see about a build's sources: url (http(s) only), kind and
        fetchedAt per source, and when the package was extracted. None without metadata."""
        meta = self._notes.get_meta(build_id)
        if meta is None:
            return None
        sources = [
            {"url": s["url"], "kind": s.get("kind") or "other", "fetchedAt": s.get("fetchedAt")}
            for s in meta.get("sources") or []
            if str(s.get("url", "")).startswith(("https://", "http://"))
        ]
        return {"sources": sources, "extractedAt": meta.get("extractedAt")}

    # -- reading ----------------------------------------------------------------------------------

    def _require(self, api: str, build: str) -> dict[str, Any]:
        notes = self._notes.get(build)
        if notes is None or notes.get("api") != api:
            raise NotFoundError(f"no release notes for build {build} of {api}")
        return notes

    def _latest(self, api: str) -> str | None:
        tag = self._tags.get(ApiId(api), TagName(LATEST))
        return tag.build_id.value if tag else None

    def get(self, api: str, build: str, full: bool = False) -> dict[str, Any]:
        """The notes. By default ``items`` holds the user-visible items only and each report
        group its first REPORT_PAGE items (page the rest with ``report_group``): a Shopify-size
        build has thousands of hidden items. ``full`` returns everything (issues, recompute)."""
        notes = self._require(api, build)
        out = {**notes, "tagged": self._latest(api) == build}
        if full:
            return out | {"report": report(notes["items"])}
        return out | {
            "items": [i for i in notes["items"] if i["visibleToUsers"]],
            "report": report(notes["items"], REPORT_PAGE),
        }

    def report_group(
        self, api: str, build: str, rule: str, cursor: int = 0, limit: int = REPORT_PAGE
    ) -> dict[str, Any]:
        """One report group, paged."""
        notes = self._require(api, build)
        group = next((g for g in report(notes["items"]) if g["rule"] == rule), None)
        if group is None:
            raise NotFoundError(f"no report group {rule!r} in these notes")
        cursor, limit = max(0, cursor), max(1, min(limit, 200))
        page = group["items"][cursor : cursor + limit]
        nxt = cursor + limit if cursor + limit < group["count"] else None
        return {"rule": rule, "count": group["count"], "items": page, "nextCursor": nxt}

    def summaries(self, api: str) -> list[dict[str, Any]]:
        latest = self._latest(api)
        return [
            {
                k: n[k]
                for k in (
                    "from",
                    "to",
                    "toDocsAsOf",
                    "computedAt",
                    "review",
                    "counts",
                    "needsAttention",
                    "attentionReason",
                )
            }
            | {"tagged": latest == n["to"], "docsUpdated": n.get("docsUpdated")}
            for n in self._notes.for_api(api)
        ]

    def issues(self, api: str, build: str, fmt: str = "markdown") -> str:
        return issues_text(self.get(api, build, full=True), "text" if fmt == "text" else "markdown")

    # -- review -----------------------------------------------------------------------------------

    def _decide(self, notes: dict[str, Any], decision: str, **more: Any) -> None:
        notes["decisions"] = [
            *notes.get("decisions", []),
            {"by": "maintainer", "at": self._now(), "decision": decision, **more},
        ]
        self._notes.save(notes)

    def _now(self) -> str:
        return self._clock.now().isoformat()

    def _move_latest(self, api: str, to: str) -> dict[str, Any]:
        target = require_build(self._builds, BuildId(to))
        current = self._tags.get(ApiId(api), TagName(LATEST))
        new = Tag.point(TagName(LATEST), target) if current is None else current.move_to(target)
        self._tags.set(new)
        return {
            "tag": LATEST,
            "buildId": to,
            "previous": current.build_id.value if current else None,
        }

    def keep(self, api: str, build: str, note: str | None = None) -> dict[str, Any]:
        """Keep the build. On a rolled-back build this rolls FORWARD (latest back to it), as long
        as latest is still its base."""
        notes = self._require(api, build)
        if notes["review"] == KEPT:
            raise ReleaseStateError(f"build {build} is already kept")
        if notes["review"] == ROLLED_BACK:
            if self._latest(api) != notes["from"]:
                raise ReleaseStateError(
                    f"latest is no longer {notes['from']}: rolling {build} forward would skip "
                    "a newer build"
                )
            self._move_latest(api, build)
            notes["review"] = KEPT
            self._decide(notes, "rollforward", note=(note or "")[:MAX_REASON] or None)
            return self.get(api, build)
        notes["review"] = KEPT
        self._decide(notes, "keep", note=(note or "")[:MAX_REASON] or None)
        return self.get(api, build)

    def rollback(self, api: str, build: str, reason: str) -> dict[str, Any]:
        """Move latest from this build back to its base; the build stays loaded."""
        reason = (reason or "").strip()
        if not reason:
            raise ReleaseStateError("a reason is required to roll back")
        notes = self._require(api, build)
        if notes["review"] == ROLLED_BACK:
            raise ReleaseStateError(f"build {build} is already rolled back")
        if self._latest(api) != build:
            raise ReleaseStateError(
                f"build {build} is not the latest of {api}: nothing to roll back"
            )
        moved = self._move_latest(api, notes["from"])
        notes["review"] = ROLLED_BACK
        self._decide(notes, "rollback", reason=reason[:MAX_REASON])
        return {**moved, "previous": build, "review": ROLLED_BACK}

    def _item(self, notes: dict[str, Any], item_id: str) -> Item:
        for it in notes["items"]:
            if it["id"] == item_id:
                return it  # type: ignore[no-any-return]
        raise NotFoundError(f"item {item_id} is not in these notes (it may have been recomputed)")

    def promote(self, api: str, build: str, item_id: str, quote: str) -> Item:
        """Confirm an item by hand with a quote that is verified against the new build's source
        (stream's snapshot of the page, or the build's own document text)."""
        notes = self._require(api, build)
        it = self._item(notes, item_id)
        doc = self._documents.get_document(BuildId(build), it["subject"]["docId"])
        sources = [
            t
            for u, t in page_texts(self._meta(build)).items()
            if it["evidence"].get("sourceUrl") and u == it["evidence"]["sourceUrl"].split("#")[0]
        ]
        if doc is not None:
            sources.append(
                f"{doc.title}\n{doc.text}\n" + " ".join(f.description or "" for f in doc.fields)
            )
        if not quote.strip() or not any(in_text(quote, t) for t in sources):
            raise QuoteNotVerifiedError("the quote is not in the new build's source for this item")
        before = copy.deepcopy(it)
        it.update(
            {
                "class": CONFIRMED,
                "visibleToUsers": not it.get("rename"),
                "promotedBy": "maintainer",
                "promotedAt": self._now(),
                "evidence": {**it["evidence"], "quote": quote.strip()[:500]},
            }
        )
        notes["counts"] = counts(notes["items"])
        self._decide(notes, "promote", item=item_id, fromClass=before["class"])
        return it

    def demote(self, api: str, build: str, item_id: str) -> Item:
        notes = self._require(api, build)
        it = self._item(notes, item_id)
        if not it.get("promotedAt"):
            raise ReleaseStateError(f"item {item_id} was not promoted")
        it["class"] = it["computedClass"]
        it["visibleToUsers"] = it["class"] in ("confirmed", "likely") and not it.get("rename")
        it["evidence"]["quote"] = None
        it.pop("promotedBy", None)
        it.pop("promotedAt", None)
        notes["counts"] = counts(notes["items"])
        self._decide(notes, "demote", item=item_id)
        return it
