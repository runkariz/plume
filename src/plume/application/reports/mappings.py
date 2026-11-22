"""Mapping reports: the reader's LLM reports a wrong or missing canonical-model mapping.

Only what the LLM sends to these calls is stored, redacted (as reported questions). A suggested
mapping runs through the same validator as submit_model_draft (its path and citation checks):
one that fails is kept as a problem with the validator's reason, never as a suggestion. The
same (concept, api, canonical field, kind) adds a note to the existing report. A maintainer
accepts a valid suggestion into a verified mapping, shown first in model sessions on that API
and re-validated whenever the API's build changes (suspended, and its report reopened, when
the field or the quote is gone).
"""

import contextlib
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from plume.application.errors import NotFoundError
from plume.application.models.concepts import concept_parts
from plume.application.models.oracle import PinnedLookups
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.mapping_repo import MappingRepo
from plume.application.ports.model_repo import ModelRepo
from plume.application.ports.search_index import FactQuery
from plume.application.reader.resolve import BuildResolver
from plume.application.reports.hosts import ApiHosts
from plume.application.reports.service import ReportRefusedError, ReportsDisabledError
from plume.domain.models.canonical_model import (
    DraftFormatError,
    name_only_as_no_quote,
    parse_draft,
)
from plume.domain.models.validation import (
    Oracle,
    quote_in,
    quote_on_field,
    substantive,
    validate,
)
from plume.domain.reports.mapping import (
    ROUTES,
    MappingKind,
    MappingReport,
    MappingStatus,
    Suggestion,
    SuggestionStatus,
    VerifiedMapping,
    VerifiedStatus,
    concept_key,
    field_key,
)
from plume.domain.reports.redact import RedactionPolicy, redact_text
from plume.domain.reports.report import (
    MAX_FIELD,
    REPORT_POLICY,
    ReportNote,
    safe_text,
    session_hash,
)
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

MAX_FOUND = 5
MAX_SUGGESTION = 4000  # characters of a suggested mapping (JSON)
# The validator's findings about a suggestion's own path and citation (type / shape / enum /
# coverage checks need the whole canonical model, which a report does not carry).
SUGGESTION_CODES = frozenset(
    {
        "DOC_NOT_FOUND",
        "ENDPOINT_NOT_FOUND",
        "FIELD_NOT_FOUND",
        "MISSING_CITATION",
        "NO_QUOTE_NOT_ALLOWED",
        "PATH_NOT_IN_FETCH",
        "QUOTE_NOT_FOUND",
        "QUOTE_NOT_ON_FIELD",
        "QUOTE_TOO_SHORT",
        "NO_SOURCES",
    }
)
ROOT_CAUSES = frozenset({"FIELD_NOT_FOUND", "DOC_NOT_FOUND"})
VERIFIED_LABEL = "verified (user report {id})"


class MappingReports:
    def __init__(
        self,
        repo: MappingRepo,
        resolver: BuildResolver,
        models: ModelRepo,
        facts: FactQuery,
        documents: DocumentRepo,
        clock: Clock,
        *,
        enabled: bool,
        salt: bytes,
        per_hour: int = 10,
        retention_days: int = 90,
        policy: RedactionPolicy = REPORT_POLICY,
        hosts: ApiHosts | None = None,
    ) -> None:
        self._hosts = hosts  # the API's own URL hosts (others are redacted); None: all stay
        self._repo = repo
        self._resolver = resolver
        self._models = models
        self._facts = facts
        self._documents = documents
        self._clock = clock
        self._enabled = enabled
        self._salt = salt
        self._per_hour = per_hour
        self._retention = timedelta(days=retention_days)
        self._policy = policy
        self._recent: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()
        self._last_purge: datetime | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _host_rule(self, api: str) -> Callable[[str], str | None] | None:
        return self._hosts.of(api) if self._hosts is not None else None

    # -- reader tools ---------------------------------------------------------------------------

    def find(self, model: str, api: str, field: str | None = None) -> dict[str, Any]:
        self._require()
        concept, _, _ = self._concept(model)
        self._resolver.resolve(api)
        reports = self._repo.find(concept, api, field, MAX_FOUND)
        verified = {field_key(m.canonical_field): m for m in self._verified(concept, api)}
        return {
            "concept": concept,
            "api": api,
            "reports": [
                self._public(r, verified.get(field_key(r.canonical_field))) for r in reports
            ],
            "verified_mappings": [
                self._verified_view(m)
                for m in verified.values()
                if m.status is VerifiedStatus.ACTIVE
                and (field is None or field_key(m.canonical_field) == field_key(field))
            ],
        }

    def report(
        self,
        model: str,
        api: str,
        canonical_field: str,
        kind: str,
        problem: str,
        current_mapping: str | None = None,
        suggested_mapping: dict[str, Any] | None = None,
        client_name: str | None = None,
        session_id: str | None = None,
        connection: str | None = None,
    ) -> dict[str, Any]:
        self._require()
        k = _checked_inputs(kind, canonical_field, problem, current_mapping, suggested_mapping)
        concept, concept_name, model_id = self._concept(model)
        build = self._resolver.resolve(api).build.build_id.value
        sess = session_hash(session_id, self._salt)
        self._limit(sess, connection)
        rule = self._host_rule(api)
        text, n_p = safe_text(problem, self._policy, rule)
        if text is None:
            raise ReportRefusedError(
                "the problem could not be stored safely: describe it in general terms, without "
                "user data (ids, order numbers, tokens, names, emails), and report again"
            )
        current, n_c = safe_text(current_mapping, self._policy, rule)
        field_name = redact_text(canonical_field.strip(), self._policy)[0][:200]
        client, _ = safe_text(client_name[:64] if client_name else None, self._policy)
        suggestion, reason = (None, None)
        if suggested_mapping is not None:
            suggestion, reason = self._check(
                concept_name, field_name, api, build, suggested_mapping
            )
        if suggested_mapping is None:
            status = SuggestionStatus.NONE
        elif suggestion is not None:
            status = SuggestionStatus.VALID
        else:
            status = SuggestionStatus.INVALID
        now = self._clock.now()
        self._maybe_purge(now)
        existing = self._repo.by_key(concept, api, field_name, k.value)
        if existing is not None:
            parts = [f"Also reported: {text}"]
            parts += [f"Current: {current}"] if current else []
            if suggested_mapping is not None:
                parts.append(
                    f"Suggested: {_described(suggestion)}"
                    if suggestion
                    else f"Suggested mapping refused: {reason}"
                )
            self._repo.add_note(
                ReportNote(
                    note_id=f"mn-{uuid.uuid4().hex[:12]}",
                    report_id=existing.report_id,
                    text="\n".join(parts),
                    created_at=now,
                    kind="duplicate",
                    client_name=client,
                    session_hash=sess,
                    build_id=build,
                    redactions=n_p + n_c,
                )
            )
            merged = self._repo.get(existing.report_id) or existing
            if suggestion is not None and merged.suggestion is None:  # a first valid suggestion
                merged = replace(
                    merged,
                    suggestion=suggestion,
                    validator_reason=None,
                    suggestion_status=SuggestionStatus.VALID,
                    build_id=build,
                )
                self._repo.save(merged)
            return {
                "id": merged.report_id,
                "merged": True,
                "message": "This mapping was already reported; your report was added to it "
                "as a note (its count went up).",
                "validation": self._validation(status, reason),
                "report": self._public(merged, None),
            }
        report = MappingReport(
            report_id=f"mr-{uuid.uuid4().hex[:12]}",
            concept=concept,
            concept_name=concept_name,
            api=api,
            canonical_field=field_name,
            kind=k,
            problem=text,
            status=MappingStatus.OPEN,
            created_at=now,
            updated_at=now,
            model_id=model_id,
            build_id=build,
            current_mapping=current,
            suggestion=suggestion,
            suggestion_status=status,
            validator_reason=reason,
            client_name=client,
            session_hash=sess,
            redactions=n_p + n_c,
        )
        self._repo.add(report, field_key(field_name))
        message = "Reported. Thank you: maintainers review mapping reports."
        if status is SuggestionStatus.INVALID:
            message += f" The suggested mapping was not stored: {reason}"
        return {
            "id": report.report_id,
            "merged": False,
            "message": message,
            "validation": self._validation(status, reason),
            "report": self._public(report, None),
        }

    def add_note(
        self,
        report_id: str,
        note: str,
        client_name: str | None = None,
        session_id: str | None = None,
        connection: str | None = None,
    ) -> dict[str, Any]:
        self._require()
        if not note.strip() or len(note) > MAX_FIELD:
            raise ReportRefusedError(f"note must be 1..{MAX_FIELD} characters")
        existing = self._repo.get(report_id)
        if existing is None:
            raise NotFoundError(f"mapping report {report_id} not found")
        sess = session_hash(session_id, self._salt)
        self._limit(sess, connection)
        text, n = safe_text(note, self._policy, self._host_rule(existing.api))
        if text is None:
            raise ReportRefusedError(
                "the note could not be stored safely: write it without user data and try again"
            )
        client, _ = safe_text(client_name[:64] if client_name else None, self._policy)
        self._repo.add_note(
            ReportNote(
                note_id=f"mn-{uuid.uuid4().hex[:12]}",
                report_id=report_id,
                text=text,
                created_at=self._clock.now(),
                client_name=client,
                session_hash=sess,
                build_id=existing.build_id,
                redactions=n,
            )
        )
        updated = self._repo.get(report_id) or existing
        return {"id": report_id, "message": "Note added.", "report": self._public(updated, None)}

    # -- sessions -------------------------------------------------------------------------------

    def for_session(self, concept_name: str, api: str) -> list[dict[str, Any]]:
        """Active verified mappings of a concept on an API, for model sessions (first)."""
        concept = concept_key(concept_parts(concept_name)[0])
        return [
            self._verified_view(m)
            for m in self._verified(concept, api)
            if m.status is VerifiedStatus.ACTIVE
        ]

    # -- maintainers ----------------------------------------------------------------------------

    def list_reports(
        self,
        api: str | None = None,
        concept: str | None = None,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        st = MappingStatus(status) if status else None
        verified = {
            (m.concept, field_key(m.canonical_field), m.api): m
            for m in self._repo.verified(concept, api)
        }
        return [
            self._full(r, verified.get((r.concept, field_key(r.canonical_field), r.api)), False)
            for r in self._repo.list_reports(api, concept, st, kind)
        ]

    def get(self, report_id: str) -> dict[str, Any]:
        r = self._repo.get(report_id)
        if r is None:
            raise NotFoundError(f"mapping report {report_id} not found")
        verified = next(iter(self._repo.verified_for(r.concept, r.api, [r.canonical_field])), None)
        return self._full(r, verified, True)

    def act(
        self, report_id: str, action: str, reason: str | None = None, route: str | None = None
    ) -> dict[str, Any]:
        r = self._repo.get(report_id)
        if r is None:
            raise NotFoundError(f"mapping report {report_id} not found")
        why, _ = safe_text(reason, self._policy) if reason else (None, 0)
        now = self._clock.now()
        if action != "reopen" and not why:
            raise ReportRefusedError("a reason is required")
        if action == "accept":
            if r.suggestion is None:
                raise ReportRefusedError(
                    "only a report with a validated suggestion can be accepted"
                )
            build = self._resolver.resolve(r.api).build.build_id.value
            problem = self._validate(r.concept_name, r.canonical_field, r.api, build, r.suggestion)
            if problem is not None:
                raise ReportRefusedError(f"the suggestion no longer validates: {problem}")
            current = next(
                iter(self._repo.verified_for(r.concept, r.api, [r.canonical_field])), None
            )
            self._repo.put_verified(
                VerifiedMapping(
                    mapping_id=current.mapping_id if current else f"vm-{uuid.uuid4().hex[:12]}",
                    concept=r.concept,
                    canonical_field=r.canonical_field,
                    api=r.api,
                    suggestion=r.suggestion,
                    build_id=build,
                    report_id=r.report_id,
                    status=VerifiedStatus.ACTIVE,
                    accepted_at=now,
                    revalidated_at=now,
                )
            )
            r = replace(r, status=MappingStatus.ACCEPTED, reason=why, route=None, updated_at=now)
        elif action == "reject":
            r = replace(r, status=MappingStatus.REJECTED, reason=why, route=None, updated_at=now)
        elif action == "route":
            if route not in ROUTES:
                raise ReportRefusedError(f"route must be one of {', '.join(ROUTES)}")
            r = replace(r, status=MappingStatus.ROUTED, reason=why, route=route, updated_at=now)
        elif action == "reopen":
            r = replace(r, status=MappingStatus.OPEN, reason=why, route=None, updated_at=now)
        else:
            raise ReportRefusedError("action must be one of accept, reject, route, reopen")
        self._repo.save(r)
        return self.get(r.report_id)

    def verified_list(
        self, concept: str | None = None, api: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        apis = {m.api for m in self._repo.verified(concept, api)}
        for a in apis:
            self.revalidate(a)
        return [self._verified_full(m) for m in self._repo.verified(concept, api, status)]

    def revalidate(self, api: str) -> dict[str, int]:
        """Re-validate an API's verified mappings against its current build: kept (moved to the
        build), or suspended with the reason (their report reopens)."""
        build = self._resolver.resolve(api).build.build_id.value
        out = {"kept": 0, "suspended": 0, "unchanged": 0}
        for m in self._repo.verified(None, api):
            if m.build_id == build:
                out["unchanged"] += 1
                continue
            problem = self._validate(m.concept, m.canonical_field, api, build, m.suggestion)
            now = self._clock.now()
            if problem is None:
                self._repo.put_verified(
                    replace(
                        m,
                        build_id=build,
                        revalidated_at=now,
                        status=VerifiedStatus.ACTIVE,
                        suspended_reason=None,
                    )
                )
                out["kept"] += 1
                continue
            self._repo.put_verified(
                replace(
                    m,
                    build_id=build,
                    revalidated_at=now,
                    status=VerifiedStatus.SUSPENDED,
                    suspended_reason=problem,
                )
            )
            report = self._repo.get(m.report_id)
            if report is not None:
                self._repo.save(
                    replace(
                        report,
                        status=MappingStatus.OPEN,
                        updated_at=now,
                        reason=f"verified mapping suspended on build {build}: {problem}",
                    )
                )
            out["suspended"] += 1
        return out

    def purge(self, older_than_days: int | None = None) -> int:
        days = self._retention.days if older_than_days is None else max(0, older_than_days)
        return self._repo.purge_open(self._clock.now() - timedelta(days=days))

    # -- helpers --------------------------------------------------------------------------------

    def _require(self) -> None:
        if not self._enabled:
            raise ReportsDisabledError("mapping reports are off on this server (PLUME_REPORTS)")

    def _concept(self, model: str) -> tuple[str, str, str | None]:
        """(concept key, concept name, model id) of a model session or a model."""
        session = self._models.get_session(model)
        if session is not None:
            return concept_key(concept_parts(session.concept)[0]), session.concept, None
        snap = self._models.get_snapshot(model)
        if snap is not None:
            return concept_key(concept_parts(snap.concept)[0]), snap.concept, snap.snapshot_id
        raise NotFoundError(f"no model session or model {model}")

    def _check(
        self, concept_name: str, field: str, api: str, build: str, raw: dict[str, Any]
    ) -> tuple[Suggestion | None, str | None]:
        """The suggestion as validated, or None and the validator's reason."""
        try:
            suggestion = _suggestion(raw)
        except (TypeError, ValueError) as exc:
            return None, f"INVALID_FORMAT: {exc}"
        problem = self._validate(concept_name, field, api, build, suggestion)
        return (None, problem) if problem else (suggestion, None)

    def _validate(
        self, concept_name: str, field: str, api: str, build: str, suggestion: Suggestion
    ) -> str | None:
        """The same validator as submit_model_draft, on a one-field draft: the first finding
        about the suggestion's path or citation, or None. An absence: see ``_absence``."""
        if suggestion.not_available:
            oracle = PinnedLookups({api: BuildId(build)}, self._facts, self._documents).oracle()
            return _absence(api, suggestion, oracle)
        name = field.rsplit(".", maxsplit=1)[-1].replace("[]", "") or "field"
        raw = {
            "name": concept_name,
            "description": "a reported mapping",
            "fields": [
                {
                    "name": name,
                    "type": "string",
                    "description": "reported",
                    "sources": {api: suggestion.draft_source()},
                }
            ],
        }
        try:
            draft = name_only_as_no_quote(parse_draft(raw))
        except DraftFormatError as exc:
            return f"INVALID_FORMAT: {exc}"
        oracle = PinnedLookups({api: BuildId(build)}, self._facts, self._documents).oracle()
        issues = [
            i for i in validate(draft, frozenset({api}), oracle) if i.code in SUGGESTION_CODES
        ]
        issues.sort(key=lambda i: i.code not in ROOT_CAUSES)  # the field / document gone first
        return f"{issues[0].code}: {issues[0].message}" if issues else None

    def _verified(self, concept: str, api: str) -> list[VerifiedMapping]:
        mappings = self._repo.verified_for(concept, api, [])
        build = self._resolver.resolve(api).build.build_id.value
        if any(m.build_id != build for m in mappings):
            self.revalidate(api)
            mappings = self._repo.verified_for(concept, api, [])
        return mappings

    def _limit(self, sess: str | None, connection: str | None) -> None:
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
        else:
            over = self._repo.writes_since(sess, since) >= self._per_hour
        if over:
            raise ReportRefusedError(
                f"this session already sent {self._per_hour} reports and notes in the last hour; "
                "please try again later"
            )

    def _maybe_purge(self, now: datetime) -> None:
        if self._last_purge is not None and now - self._last_purge < timedelta(days=1):
            return
        self._last_purge = now
        with contextlib.suppress(Exception):  # retention must never fail a report
            self._repo.purge_open(now - self._retention)

    @staticmethod
    def _validation(status: SuggestionStatus, reason: str | None) -> dict[str, Any] | None:
        if status is SuggestionStatus.NONE:
            return None
        return {"ok": status is SuggestionStatus.VALID, "reason": reason}

    @staticmethod
    def _verified_view(m: VerifiedMapping) -> dict[str, Any]:
        out = {
            "id": m.mapping_id,
            "canonical_field": m.canonical_field,
            **m.suggestion.as_json(),
            "label": VERIFIED_LABEL.format(id=m.report_id),
            "report_id": m.report_id,
            "build": m.build_id,
        }
        if m.suggestion.not_available:
            avoid = ", ".join(m.suggestion.not_from)
            out["note"] = "Not available on this API: map no source for it here" + (
                f" (not {avoid})" if avoid else ""
            )
        return out

    @staticmethod
    def _verified_full(m: VerifiedMapping) -> dict[str, Any]:
        return {
            "id": m.mapping_id,
            "concept": m.concept,
            "canonical_field": m.canonical_field,
            "api": m.api,
            **m.suggestion.as_json(),
            "build": m.build_id,
            "report_id": m.report_id,
            "suspended": m.status is VerifiedStatus.SUSPENDED,
            "suspended_reason": m.suspended_reason,
            "accepted_at": m.accepted_at.isoformat(),
            "validated_at": m.revalidated_at.isoformat(),
        }

    @staticmethod
    def _public(r: MappingReport, verified: VerifiedMapping | None) -> dict[str, Any]:
        """What readers see: field, kind, status (with the reason once decided), counts, and
        the verified mapping when there is one."""
        out: dict[str, Any] = {
            "id": r.report_id,
            "canonical_field": r.canonical_field,
            "kind": r.kind.value,
            "status": r.status.value,
            "report_count": r.report_count,
        }
        if r.status in (MappingStatus.ACCEPTED, MappingStatus.REJECTED) and r.reason:
            out["reason"] = r.reason
        if verified is not None and verified.status is VerifiedStatus.ACTIVE:
            out["verified_mapping"] = MappingReports._verified_view(verified)
        return out

    def _full(
        self, r: MappingReport, verified: VerifiedMapping | None, with_notes: bool
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": r.report_id,
            "concept": r.concept,
            "concept_name": r.concept_name,
            "model_id": r.model_id,
            "api": r.api,
            "build": r.build_id,
            "canonical_field": r.canonical_field,
            "kind": r.kind.value,
            "status": r.status.value,
            "route": r.route,
            "reason": r.reason,
            "problem": r.problem,
            "current_mapping": r.current_mapping,
            "suggestion": r.suggestion.as_json() if r.suggestion else None,
            "validation": self._validation(r.suggestion_status, r.validator_reason),
            "verified": None
            if verified is None
            else {
                "id": verified.mapping_id,
                "report_id": verified.report_id,
                "build": verified.build_id,
                "validated_at": verified.revalidated_at.isoformat(),
                "suspended": verified.status is VerifiedStatus.SUSPENDED,
                "suspended_reason": verified.suspended_reason,
            },
            "report_count": r.report_count,
            "note_count": r.note_count,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
            "client_name": r.client_name,
            "session_hash": r.session_hash,
            "redactions": r.redactions,
        }
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


def _described(suggestion: Suggestion) -> str:
    if suggestion.not_available:
        avoid = ", ".join(suggestion.not_from)
        return "not available" + (f" (not {avoid})" if avoid else "")
    return ", ".join(suggestion.paths)


def _absence(api: str, suggestion: Suggestion, oracle: Oracle) -> str | None:
    """A documented absence, checked as citations are: at least one quote, each in its
    document and carrying information (noQuote cannot prove an absence); each notFrom path a
    documented field, and then a quote about one of them (its own description says what it is)."""
    if not suggestion.evidence:
        return "MISSING_CITATION: an absence needs a quote saying what the API has instead"
    for p in suggestion.not_from:
        if not oracle.field_exists(api, p):
            return f"FIELD_NOT_FOUND: {p} is not a documented field of {api}"
    about = False
    for e in suggestion.evidence:
        problem = _citation_problem(api, e, oracle)
        if problem is not None:
            return problem
        quote = e.get("quote") or ""
        about = (
            about
            or not suggestion.not_from
            or quote_on_field(quote, list(suggestion.not_from), api, e["docId"], oracle)
        )
    if not about:
        return (
            "QUOTE_NOT_ON_FIELD: quote the own description of "
            f"{', '.join(suggestion.not_from)} (what it is instead)"
        )
    return None


def _citation_problem(api: str, e: dict[str, Any], oracle: Oracle) -> str | None:
    """One citation of an absence: in the build, quoted (not noQuote), in it, informative."""
    text = oracle.doc_text(api, e["docId"])
    quote = e.get("quote") or ""
    if text is None:
        return f"DOC_NOT_FOUND: {e['docId']} is not in the build"
    if not quote:
        return "NO_QUOTE_NOT_ALLOWED: an absence needs a quote, not noQuote"
    if not quote_in(quote, text):
        return f"QUOTE_NOT_FOUND: the quote is not in {e['docId']}: {quote[:80]!r}"
    if not substantive(quote):
        return f"QUOTE_TOO_SHORT: the quote carries no information ({quote[:40]!r})"
    return None


def _checked_inputs(
    kind: str,
    canonical_field: str,
    problem: str,
    current_mapping: str | None,
    suggested_mapping: dict[str, Any] | None,
) -> MappingKind:
    """The kind, after the lengths and required fields are checked (a polite refusal)."""
    try:
        k = MappingKind(kind)
    except ValueError as exc:
        kinds = ", ".join(x.value for x in MappingKind)
        raise ReportRefusedError(f"kind must be one of {kinds}") from exc
    for name, value, required in (
        ("canonical_field", canonical_field, True),
        ("problem", problem, True),
        ("current_mapping", current_mapping, False),
    ):
        if required and not (value or "").strip():
            raise ReportRefusedError(f"{name} is required")
        if value is not None and len(value) > MAX_FIELD:
            raise ReportRefusedError(f"{name} is longer than {MAX_FIELD} characters")
    if suggested_mapping is not None and len(json.dumps(suggested_mapping)) > MAX_SUGGESTION:
        raise ReportRefusedError(f"suggested_mapping is longer than {MAX_SUGGESTION} characters")
    return k


def _suggestion(raw: dict[str, Any]) -> Suggestion:
    """A suggested mapping as a draft source: {paths | path, evidence: [{doc_id | docId,
    quote | noQuote}], fetch?}, or an absence: {notAvailable: true, notFrom?: [paths],
    evidence: [{doc_id, quote}]}."""
    if not isinstance(raw, dict):
        raise TypeError("suggested_mapping must be an object")
    listed = raw.get("paths") or ([raw["path"]] if isinstance(raw.get("path"), str) else [])
    paths = [p.get("path") if isinstance(p, dict) else p for p in listed]  # draft path objects
    absent = raw.get("notAvailable") is True or raw.get("not_available") is True
    not_from = raw.get("notFrom") or raw.get("not_from") or []
    if isinstance(not_from, str):
        not_from = [not_from]
    if absent and paths:
        raise ValueError("a notAvailable suggestion has no paths (name wrong ones in notFrom)")
    if not absent and (not paths or not all(isinstance(p, str) and p.strip() for p in paths)):
        raise ValueError(
            "suggested_mapping needs paths: the source field path(s) on that API, or "
            '"notAvailable": true with a quote'
        )
    if not all(isinstance(p, str) and p.strip() for p in not_from):
        raise ValueError("notFrom lists source field paths (strings)")
    evidence = raw.get("evidence") or []
    if isinstance(evidence, dict):
        evidence = [evidence]
    out = []
    for e in evidence:
        if not isinstance(e, dict):
            raise TypeError("evidence entries must be objects")
        doc = e.get("doc_id") or e.get("docId")
        if not isinstance(doc, str) or not doc:
            raise ValueError("each evidence needs doc_id")
        out.append(
            {
                "docId": doc,
                "quote": e.get("quote") if isinstance(e.get("quote"), str) else None,
                "noQuote": e.get("noQuote") if isinstance(e.get("noQuote"), str) else None,
            }
        )
    fetch = raw.get("fetch") if isinstance(raw.get("fetch"), str) else None
    return Suggestion(
        tuple(str(p).strip() for p in paths),
        tuple(out),
        None if absent else fetch,
        absent,
        tuple(str(p).strip() for p in not_from),
    )
