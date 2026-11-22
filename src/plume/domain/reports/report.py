"""A reported question and its notes, and the rules for the text they keep."""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from plume.domain.reports.redact import (
    _EMAIL,
    _JWT,
    _LONG_KEYLIKE,
    _PREFIXED,
    RedactionPolicy,
    redact_text,
)

MAX_FIELD = 1000  # characters per field, before redaction

# The owner's choices for reports (2026-11-21): error codes and the RPC `method` value stay.
REPORT_POLICY = RedactionPolicy(keep_error_codes=True, keep_rpc_method=True)


class ReportStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    SEARCH_MISS = "search-miss"
    PACKAGE_GAP = "package-gap"
    OUT_OF_SCOPE = "out-of-scope"


@dataclass(frozen=True, slots=True)
class ReportNote:
    note_id: str
    report_id: str
    text: str
    created_at: datetime
    kind: str = "note"  # note | duplicate (a near-duplicate report merged in)
    client_name: str | None = None
    session_hash: str | None = None
    build_id: str | None = None
    redactions: int = 0


@dataclass(frozen=True, slots=True)
class Report:
    report_id: str
    api: str
    question: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    build_id: str | None = None
    what_was_tried: str | None = None
    what_was_missing: str | None = None
    reason: str | None = None  # the maintainer's short reason for the status
    report_count: int = 1  # the report itself plus merged near-duplicates and notes
    note_count: int = 0
    client_name: str | None = None
    session_hash: str | None = None
    redactions: int = 0


class ReportTextError(ValueError):
    """A field is too long or empty."""


def session_hash(session_id: str | None, salt: bytes) -> str | None:
    """A session id as a keyed hash: groups one conversation, identifies no one."""
    if not session_id:
        return None
    return hmac.new(salt, session_id.encode(), hashlib.sha256).hexdigest()[:16]


_STILL_UNSAFE = (_JWT, _PREFIXED, _EMAIL, re.compile(r"\d{9,}"))
_MARKER = re.compile(r"\[(?:token|secret|email|account|ip|number|query|company|id)\]")


def safe_text(text: str | None, policy: RedactionPolicy = REPORT_POLICY) -> tuple[str | None, int]:
    """The field as it may be stored: redacted, or None when the rules cannot make it safe
    (something secret-looking survives, or it is mostly redaction markers)."""
    if text is None or not text.strip():
        return None, 0
    red, n = redact_text(text.strip(), policy)
    if any(p.search(red) for p in _STILL_UNSAFE) or any(
        _LONG_KEYLIKE.fullmatch(w) and any(c.isdigit() for c in w) for w in red.split()
    ):
        return None, n + 1
    words = red.split()
    marks = sum(1 for w in words if _MARKER.search(w))
    if words and marks * 2 > len(words):  # mostly markers: nothing general left to keep
        return None, n
    return red, n


def check_length(name: str, text: str | None, required: bool = False) -> None:
    if required and (text is None or not text.strip()):
        raise ReportTextError(f"{name} is required")
    if text is not None and len(text) > MAX_FIELD:
        raise ReportTextError(f"{name} is longer than {MAX_FIELD} characters")


def duplicate_key(question: str) -> str:
    """The question compared as text: case, punctuation and spacing ignored."""
    return " ".join(re.findall(r"[a-z0-9]+", question.lower()))
