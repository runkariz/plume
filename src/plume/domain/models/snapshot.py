"""An immutable, validated canonical model pinned to builds."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from plume.domain.models.canonical_model import ModelDraft
from plume.domain.shared.hashing import content_hash

PROMPT_VERSION = "plume-models-v1"


class Visibility:
    """official = released by a maintainer, listed publicly; unreleased = written for (or by) a
    maintainer, waiting for review; unlisted = a user's model, readable by anyone with its id;
    discarded = an unreleased model the maintainer threw away."""

    OFFICIAL = "official"
    UNRELEASED = "unreleased"
    UNLISTED = "unlisted"
    DISCARDED = "discarded"
    ALL = (OFFICIAL, UNRELEASED, UNLISTED, DISCARDED)
    PUBLIC = (OFFICIAL, UNLISTED)  # readable without the maintainer token (by id)


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

    @property
    def lineage(self) -> str:
        return self.lineage_id or self.snapshot_id

    @property
    def key(self) -> str:
        return self.content_key or self.snapshot_id

    def support(self, api: str) -> dict[str, str]:
        """Per canonical field: supported | derived | unsupported for this API."""
        out = {}
        for f in self.draft.fields:
            src = f.source(api)
            out[f.name] = (
                "unsupported" if src is None else "derived" if src.derived else "supported"
            )
        return out

    def coverage(self) -> dict[str, tuple[int, int]]:
        total = len(self.draft.fields)
        return {
            i.api: (sum(1 for v in self.support(i.api).values() if v != "unsupported"), total)
            for i in self.inputs
        }


def draft_json(draft: ModelDraft) -> dict[str, Any]:
    return {
        "name": draft.name,
        "description": draft.description,
        "fields": [
            {
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
                            {"doc_id": e.doc_id, "quote": e.quote, "anchor": e.anchor}
                            for e in s.evidence
                        ],
                    }
                    for api, s in f.sources
                },
            }
            for f in draft.fields
        ],
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
