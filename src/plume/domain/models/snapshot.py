"""An immutable, validated canonical model pinned to builds."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from plume.domain.models.canonical_model import CanonicalField, ModelDraft
from plume.domain.models.validation import Issue
from plume.domain.shared.hashing import content_hash

PROMPT_VERSION = "plume-models-v1"


class Visibility:
    """official = released by a maintainer, listed publicly; unreleased = written for (or by) a
    maintainer, waiting for review; unlisted = a user's model, readable by anyone with its id;
    discarded = an unreleased model the maintainer threw away; superseded = an official model a
    maintainer replaced with a newer one at release (readable by id, not listed)."""

    OFFICIAL = "official"
    UNRELEASED = "unreleased"
    UNLISTED = "unlisted"
    DISCARDED = "discarded"
    SUPERSEDED = "superseded"
    ALL = (OFFICIAL, UNRELEASED, UNLISTED, DISCARDED, SUPERSEDED)
    PUBLIC = (OFFICIAL, UNLISTED, SUPERSEDED)  # readable without the maintainer token (by id)


class Origin:
    USER = "user"
    MAINTAINER = "maintainer"


@dataclass(frozen=True, slots=True)
class PinnedInput:
    api: str
    build: str


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    snapshot_id: str
    session_id: str
    concept: str
    inputs: tuple[PinnedInput, ...]
    draft: ModelDraft
    created_at: datetime
    citations_checked: int
    prompt_version: str = PROMPT_VERSION
    status: str = "generated_unverified"
    visibility: str = Visibility.OFFICIAL
    origin: str = Origin.MAINTAINER
    generator: str = "claude"
    lineage_id: str = ""  # "" = this snapshot starts its own lineage
    version: int = 1
    based_on: str | None = None
    content_key: str = ""  # snapshot_id_for(...) of the content ("" = the snapshot id)
    released_at: datetime | None = None
    generator_usage: dict[str, int] | None = None  # LLM tokens spent writing it (server generation)
    warnings: tuple[Issue, ...] = ()  # validation warnings (WRITE_ONLY_SOURCE, ...)
    superseded_by: str | None = None  # the official model that replaced it at its release
    superseded_at: datetime | None = None

    @property
    def lineage(self) -> str:
        return self.lineage_id or self.snapshot_id

    @property
    def key(self) -> str:
        return self.content_key or self.snapshot_id

    def support(self, api: str) -> dict[str, str]:
        """Per canonical field (by canonical path, nested ones included): supported | derived |
        unsupported for this API. A container is supported when it or any sub-field is."""
        out: dict[str, str] = {}
        for path, f in reversed(self.draft.walk()):  # children before their parent
            src = f.source(api)
            own = "unsupported" if src is None else "derived" if src.derived else "supported"
            if f.fields and own == "unsupported":
                kids = [out[f"{f.child_path(path)}.{c.name}"] for c in f.fields]
                own = "derived" if any(k != "unsupported" for k in kids) else "unsupported"
            out[path] = own
        return out

    def coverage(self) -> dict[str, tuple[int, int]]:
        """Mapped leaves / all leaves per API (containers are not counted)."""
        leaves = [p for p, _ in self.draft.leaves()]
        total = len(leaves)
        out = {}
        for i in self.inputs:
            support = self.support(i.api)
            out[i.api] = (sum(1 for p in leaves if support[p] != "unsupported"), total)
        return out


def _field_json(f: CanonicalField) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": f.name,
        "type": f.type,
        "description": f.description,
        "required": f.required,
        "sources": {
            api: {
                "paths": [{"path": p.path, "type": p.type} for p in s.paths],
                "fetch": s.fetch,
                "join": list(s.join),
                "transform": s.transform,
                "evidence": [
                    {"doc_id": e.doc_id, "quote": e.quote, "anchor": e.anchor} for e in s.evidence
                ],
            }
            for api, s in f.sources
        },
    }
    if f.fields:  # only when present, so models without nesting keep their content hash
        out["fields"] = [_field_json(c) for c in f.fields]
    return out


def draft_json(draft: ModelDraft) -> dict[str, Any]:
    return {
        "name": draft.name,
        "description": draft.description,
        "fields": [_field_json(f) for f in draft.fields],
        "open_questions": [
            {"question": q.question, "detail": q.detail, "options": list(q.options)}
            for q in draft.open_questions
        ],
    }


def snapshot_id_for(inputs: tuple[PinnedInput, ...], concept: str, draft: ModelDraft) -> str:
    """Same pinned builds + same validated model = same snapshot (idempotent submit)."""
    payload = json.dumps(
        {
            "inputs": [[i.api, i.build] for i in sorted(inputs, key=lambda i: i.api)],
            "concept": concept,
            "model": draft_json(draft),
            "prompt_version": PROMPT_VERSION,
        },
        sort_keys=True,
    )
    return "m-" + content_hash(payload).short(24)
