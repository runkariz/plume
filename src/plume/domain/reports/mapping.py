"""Mapping reports: what a reader's LLM reports about a canonical model's mapping, and the
verified mappings a maintainer accepts from them."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class MappingKind(StrEnum):
    WRONG = "wrong"
    MISSING = "missing"
    MODEL_FIELD_MISSING = "model-field-missing"


class MappingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROUTED = "routed"  # sent on: plume (context missed it), stream (not in the package), owner


class SuggestionStatus(StrEnum):
    NONE = "none"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A suggested source on one API, in a draft mapping's shape (paths + citations), or a
    documented absence: the field is not available on that API (``not_from``: documented paths
    it must not be mapped from, which the quote describes as something else)."""

    paths: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]  # {docId, quote | None, noQuote | None}
    fetch: str | None = None
    not_available: bool = False
    not_from: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {"paths": list(self.paths), "fetch": self.fetch, "evidence": list(self.evidence),
                "notAvailable": self.not_available, "notFrom": list(self.not_from)}  # fmt: skip

    def draft_source(self) -> dict[str, Any]:
        """The source as submit_model_draft takes it."""
        ev = [
            {"doc_id": e["docId"], **({"noQuote": e["noQuote"]} if e.get("noQuote")
                                      else {"quote": e.get("quote") or ""})}
            for e in self.evidence
        ]  # fmt: skip
        out: dict[str, Any] = {"paths": list(self.paths), "evidence": ev}
        if self.fetch:
            out["fetch"] = self.fetch
        return out


@dataclass(frozen=True, slots=True)
class MappingReport:
    report_id: str
    concept: str  # the concept's key ("inventory/stock")
    concept_name: str  # as named in the session or model
    api: str
    canonical_field: str
    kind: MappingKind
    problem: str
    status: MappingStatus
    created_at: datetime
    updated_at: datetime
    model_id: str | None = None
    build_id: str | None = None
    current_mapping: str | None = None
    suggestion: Suggestion | None = None
    suggestion_status: SuggestionStatus = SuggestionStatus.NONE
    validator_reason: str | None = None
    reason: str | None = None
    route: str | None = None  # plume | stream | owner, when routed
    report_count: int = 1
    note_count: int = 0
    client_name: str | None = None
    session_hash: str | None = None
    redactions: int = 0


ROUTES = ("plume", "stream", "owner")


class VerifiedStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class VerifiedMapping:
    mapping_id: str
    concept: str
    canonical_field: str
    api: str
    suggestion: Suggestion
    build_id: str  # the build it was last validated on
    report_id: str
    status: VerifiedStatus
    accepted_at: datetime
    revalidated_at: datetime
    suspended_reason: str | None = None


def concept_key(main: tuple[str, ...]) -> str:
    """A concept's identity across sessions: its main parts ("inventory/stock")."""
    return "/".join(main)


def same_concept(a: str, b: str) -> bool:
    """One concept key is the other or its main part: product ~ product/offer, inventory ~
    inventory/stock (siblings such as inventory/stock and inventory/level are not)."""
    return a == b or a.startswith(f"{b}/") or b.startswith(f"{a}/")


def field_key(name: str) -> str:
    """A canonical field compared loosely: case, list marks and separators ignored."""
    return re.sub(r"[^a-z0-9.]", "", name.lower().replace("[]", ""))
