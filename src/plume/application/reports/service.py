"""Reported questions: the reader's LLM reports what Plume could not answer.

Only what the LLM sends to these calls is stored (never the chat, never any other tool call),
and only after redaction; a field the rules cannot make safe is refused (the question) or left
out (the other fields). A near-duplicate of an existing report (the same words, or embeddings
at least ``duplicate_similarity`` apart) becomes a note on it. Each session may write at most
``per_hour`` reports and notes an hour. Open reports untouched for ``retention_days`` are
purged (lazily, at most once a day); triaged ones stay.
"""

import contextlib
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.embedder import Embedder
from plume.application.ports.report_repo import ReportRepo
from plume.application.reader.resolve import BuildResolver
from plume.application.reports.hosts import ApiHosts
from plume.domain.reports.redact import RedactionPolicy, redact_text
from plume.domain.reports.report import (
    REPORT_POLICY,
    Report,
    ReportNote,
    ReportStatus,
    ReportTextError,
    check_length,
    duplicate_key,
    safe_text,
    session_hash,
)
from plume.domain.shared.clock import Clock

MAX_SIMILAR = 5
MAX_TRACKED = 10_000  # connections whose hourly writes are counted in memory
PURGE_EVERY = timedelta(days=1)
STATUS_SHOWN = {ReportStatus.ANSWERED, ReportStatus.OUT_OF_SCOPE}  # their reason is public


class ReportsDisabledError(ApplicationError):
    pass


class ReportRefusedError(ApplicationError, ValueError):
    """Too long, unsafe, or over the session's hourly limit (a polite refusal)."""


class ReportedQuestions:
    def __init__(
        self,
        repo: ReportRepo,
        embedder: Embedder,
        resolver: BuildResolver,
        clock: Clock,
        *,
        enabled: bool,
        salt: bytes,
        per_hour: int = 10,
        retention_days: int = 90,
        duplicate_similarity: float = 0.92,
        policy: RedactionPolicy = REPORT_POLICY,
        hosts: ApiHosts | None = None,
    ) -> None:
        self._hosts = hosts  # the API's own URL hosts (others are redacted); None: all stay
        self._repo = repo
        self._embedder = embedder
        self._resolver = resolver
        self._clock = clock
        self._enabled = enabled
        self._salt = salt
        self._per_hour = per_hour
        self._retention = timedelta(days=retention_days)
        self._duplicate = duplicate_similarity
        self._policy = policy
        self._last_purge: datetime | None = None
        self._recent: dict[str, list[datetime]] = {}  # connection key -> write times (memory)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _host_rule(self, api: str) -> Callable[[str], str | None] | None:
        return self._hosts.of(api) if self._hosts is not None else None

    # -- reader tools ---------------------------------------------------------------------------

    def find(self, api: str, question: str) -> dict[str, Any]:
        self._require()
        self._resolver.resolve(api)  # an unknown API is an error
        check_length("question", question, required=True)
        text, _ = redact_text(question, self._policy)
        similar = self._similar(api, text, MAX_SIMILAR)
        return {"api": api, "similar": [self._public(r, score) for r, score in similar]}

    def report(
        self,
        api: str,
        question: str,
        what_was_tried: str | None,
        what_was_missing: str | None,
        client_name: str | None = None,
        session_id: str | None = None,
        connection: str | None = None,
    ) -> dict[str, Any]:
        """``connection``: the caller's address, only to count its hourly limit in memory when
        there is no session id (stateless clients); never stored."""
        self._require()
        for name, value, required in (("question", question, True),
                                      ("what_was_tried", what_was_tried, False),
                                      ("what_was_missing", what_was_missing, False)):  # fmt: skip
            self._check(name, value, required)
        build = self._resolver.resolve(api).build.build_id.value
        sess = session_hash(session_id, self._salt)
        self._limit(sess, connection)
        rule = self._host_rule(api)
        q, n_q = safe_text(question, self._policy, rule)
        if q is None:
            raise ReportRefusedError(
                "the question could not be stored safely: write it in general terms, without "
                "user data (ids, order numbers, tokens, names, emails), and report again"
            )
        tried, n_t = safe_text(what_was_tried, self._policy, rule)
        missing, n_m = safe_text(what_was_missing, self._policy, rule)
        client, n_c = safe_text(client_name[:64] if client_name else None, self._policy)
        now = self._clock.now()
        self._maybe_purge(now)
        existing = self._repo.by_key(api, duplicate_key(q))
        vector = self._embed(q)
        if existing is None and vector is not None:
            near = self._repo.similar(api, vector, self._embedder.model, 1)
            if near and near[0][1] >= self._duplicate:
                existing = near[0][0]
        if existing is not None:
            parts = [f"Also reported as: {q}"]
            parts += [f"Tried: {tried}"] if tried else []
            parts += [f"Missing: {missing}"] if missing else []
            self._repo.add_note(ReportNote(
                note_id=f"rn-{uuid.uuid4().hex[:12]}", report_id=existing.report_id,
                text="\n".join(parts), created_at=now, kind="duplicate", client_name=client,
                session_hash=sess, build_id=build, redactions=n_q + n_t + n_m + n_c,
            ))  # fmt: skip
            merged = self._repo.get(existing.report_id) or existing
            return {
                "id": merged.report_id,
                "merged": True,
                "message": "A very similar question was already reported; your report was "
                "added to it as a note (its report count went up).",
                "report": self._public(merged, None),
            }
        report = Report(
            report_id=f"rq-{uuid.uuid4().hex[:12]}", api=api, question=q,
            status=ReportStatus.OPEN, created_at=now, updated_at=now, build_id=build,
            what_was_tried=tried, what_was_missing=missing, client_name=client,
            session_hash=sess, redactions=n_q + n_t + n_m + n_c,
        )  # fmt: skip
        self._repo.add(report, duplicate_key(q), vector, self._embedder.model)
        return {"id": report.report_id, "merged": False,
                "message": "Reported. Thank you: maintainers review reported questions.",
                "report": self._public(report, None)}  # fmt: skip

    def add_note(
        self,
        report_id: str,
        note: str,
        client_name: str | None = None,
        session_id: str | None = None,
        connection: str | None = None,
    ) -> dict[str, Any]:
        self._require()
        self._check("note", note, True)
        existing = self._repo.get(report_id)
        if existing is None:
            raise NotFoundError(f"reported question {report_id} not found")
        sess = session_hash(session_id, self._salt)
        self._limit(sess, connection)
        text, n = safe_text(note, self._policy, self._host_rule(existing.api))
        if text is None:
            raise ReportRefusedError(
                "the note could not be stored safely: write it without user data and try again"
            )
        client, n_c = safe_text(client_name[:64] if client_name else None, self._policy)
        now = self._clock.now()
        self._repo.add_note(ReportNote(
            note_id=f"rn-{uuid.uuid4().hex[:12]}", report_id=report_id, text=text,
            created_at=now, client_name=client, session_hash=sess, build_id=existing.build_id,
            redactions=n + n_c,
        ))  # fmt: skip
        updated = self._repo.get(report_id) or existing
        return {"id": report_id, "message": "Note added.", "report": self._public(updated, None)}

    # -- maintainers ----------------------------------------------------------------------------

    def list_reports(
        self, api: str | None = None, status: str | None = None, since: datetime | None = None
    ) -> Iterator[dict[str, Any]]:
        for r in self._repo.list(api, ReportStatus(status) if status else None, since):
            yield self._full(r, with_notes=False)

    def get(self, report_id: str) -> dict[str, Any]:
        r = self._repo.get(report_id)
        if r is None:
            raise NotFoundError(f"reported question {report_id} not found")
        return self._full(r, with_notes=True)

    def set_status(self, report_id: str, status: str, reason: str | None = None) -> dict[str, Any]:
        try:
            value = ReportStatus(status)
        except ValueError as exc:
            allowed = ", ".join(s.value for s in ReportStatus)
            raise ReportRefusedError(f"status must be one of {allowed}") from exc
        self._check("reason", reason, False)
        text, _ = safe_text(reason, self._policy)
        if not self._repo.set_status(report_id, value, text, self._clock.now()):
            raise NotFoundError(f"reported question {report_id} not found")
        return self.get(report_id)

    def purge(self, older_than_days: int | None = None) -> int:
        days = self._retention.days if older_than_days is None else max(0, older_than_days)
        return self._repo.purge_open(self._clock.now() - timedelta(days=days))

    # -- helpers --------------------------------------------------------------------------------

    def _require(self) -> None:
        if not self._enabled:
            raise ReportsDisabledError("reported questions are off on this server (PLUME_REPORTS)")

    def _check(self, name: str, value: str | None, required: bool) -> None:
        try:
            check_length(name, value, required)
        except ReportTextError as exc:
            raise ReportRefusedError(str(exc)) from exc

    def _limit(self, sess: str | None, connection: str | None) -> None:
        """At most per_hour reports and notes an hour: per session (counted in the store) or,
        without a session id, per connection (counted in memory under a keyed hash of the
        address, never stored)."""
        now = self._clock.now()
        since = now - timedelta(hours=1)
        if sess is None and connection:
            key = session_hash(f"addr:{connection}", self._salt) or ""
            with self._lock:
                recent = [t for t in self._recent.get(key, []) if t >= since]
                over = len(recent) >= self._per_hour
                if not over:
                    recent.append(now)
                self._recent[key] = recent
                if len(self._recent) > MAX_TRACKED:  # forget idle connections
                    self._recent = {k: v for k, v in self._recent.items() if v and v[-1] >= since}
        else:
            over = self._repo.writes_since(sess, since) >= self._per_hour
        if over:
            raise ReportRefusedError(
                f"this session already sent {self._per_hour} reports and notes in the last hour; "
                "please try again later"
            )

    def _embed(self, text: str) -> list[float] | None:
        try:
            return list(self._embedder.embed_query(text))
        except Exception:
            return None

    def _similar(self, api: str, text: str, limit: int) -> list[tuple[Report, float]]:
        vector = self._embed(text)
        found: list[tuple[Report, float]] = (
            self._repo.similar(api, vector, self._embedder.model, limit) if vector else []
        )
        exact = self._repo.by_key(api, duplicate_key(text))
        if exact is not None and all(r.report_id != exact.report_id for r, _ in found):
            found = [(exact, 1.0), *found][:limit]
        return found

    def _maybe_purge(self, now: datetime) -> None:
        if self._last_purge is not None and now - self._last_purge < PURGE_EVERY:
            return
        self._last_purge = now
        with contextlib.suppress(Exception):  # retention must never fail a report
            self._repo.purge_open(now - self._retention)

    @staticmethod
    def _public(r: Report, similarity: float | None) -> dict[str, Any]:
        """What readers see: the redacted question, status (and the public reason), counts."""
        out: dict[str, Any] = {
            "id": r.report_id, "question": r.question, "status": r.status.value,
            "report_count": r.report_count, "note_count": r.note_count,
        }  # fmt: skip
        if r.status in STATUS_SHOWN and r.reason:
            out["reason"] = r.reason
        if similarity is not None:
            out["similarity"] = round(similarity, 3)
        return out

    def _full(self, r: Report, with_notes: bool) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": r.report_id, "api": r.api, "build": r.build_id, "question": r.question,
            "what_was_tried": r.what_was_tried, "what_was_missing": r.what_was_missing,
            "status": r.status.value, "reason": r.reason, "report_count": r.report_count,
            "note_count": r.note_count, "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(), "client_name": r.client_name,
            "session_hash": r.session_hash, "redactions": r.redactions,
        }  # fmt: skip
        if with_notes:
            out["notes"] = [
                {
                    "id": n.note_id,
                    "kind": n.kind,
                    "text": n.text,
                    "created_at": n.created_at.isoformat(),
                    "client_name": n.client_name,
                    "session_hash": n.session_hash,
                    "build": n.build_id,
                    "redactions": n.redactions,
                }
                for n in self._repo.notes(r.report_id)
            ]
        return out
