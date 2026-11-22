import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from plume.domain.reports.mapping import (
    MappingKind,
    MappingReport,
    MappingStatus,
    Suggestion,
    SuggestionStatus,
    VerifiedMapping,
    VerifiedStatus,
    field_key,
)
from plume.domain.reports.report import ReportNote

_COLS = (
    "report_id, concept, concept_name, model_id, api, build_id, canonical_field, kind, problem, "
    "current_mapping, suggestion, suggestion_status, validator_reason, status, reason, route, "
    "report_count, note_count, created_at, updated_at, client_name, session_hash, redactions"
)
_VCOLS = (
    "mapping_id, concept, canonical_field, api, suggestion, build_id, report_id, status, "
    "suspended_reason, accepted_at, revalidated_at"
)


def _suggestion(raw: Any) -> Suggestion | None:
    if not raw:
        return None
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return Suggestion(
        tuple(data.get("paths") or ()),
        tuple(data.get("evidence") or ()),
        data.get("fetch"),
        data.get("notAvailable") is True,
        tuple(data.get("notFrom") or ()),
    )


def _report(r: Any) -> MappingReport:
    return MappingReport(
        report_id=r.report_id,
        concept=r.concept,
        concept_name=r.concept_name,
        api=r.api,
        canonical_field=r.canonical_field,
        kind=MappingKind(r.kind),
        problem=r.problem,
        status=MappingStatus(r.status),
        created_at=r.created_at,
        updated_at=r.updated_at,
        model_id=r.model_id,
        build_id=r.build_id,
        current_mapping=r.current_mapping,
        suggestion=_suggestion(r.suggestion),
        suggestion_status=SuggestionStatus(r.suggestion_status),
        validator_reason=r.validator_reason,
        reason=r.reason,
        route=r.route,
        report_count=r.report_count,
        note_count=r.note_count,
        client_name=r.client_name,
        session_hash=r.session_hash,
        redactions=r.redactions,
    )


def _verified(r: Any) -> VerifiedMapping:
    suggestion = _suggestion(r.suggestion) or Suggestion((), ())
    return VerifiedMapping(
        mapping_id=r.mapping_id,
        concept=r.concept,
        canonical_field=r.canonical_field,
        api=r.api,
        suggestion=suggestion,
        build_id=r.build_id,
        report_id=r.report_id,
        status=VerifiedStatus(r.status),
        accepted_at=r.accepted_at,
        revalidated_at=r.revalidated_at,
        suspended_reason=r.suspended_reason,
    )


def _params(r: MappingReport) -> dict[str, Any]:
    return {
        "report_id": r.report_id,
        "concept": r.concept,
        "concept_name": r.concept_name,
        "model_id": r.model_id,
        "api": r.api,
        "build_id": r.build_id,
        "canonical_field": r.canonical_field,
        "field_key": field_key(r.canonical_field),
        "kind": r.kind.value,
        "problem": r.problem,
        "current_mapping": r.current_mapping,
        "suggestion": json.dumps(r.suggestion.as_json()) if r.suggestion else None,
        "suggestion_status": r.suggestion_status.value,
        "validator_reason": r.validator_reason,
        "status": r.status.value,
        "reason": r.reason,
        "route": r.route,
        "report_count": r.report_count,
        "note_count": r.note_count,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "client_name": r.client_name,
        "session_hash": r.session_hash,
        "redactions": r.redactions,
    }


class PostgresMappingRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _reports(self, where: str, params: dict[str, Any], tail: str = "") -> list[MappingReport]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {_COLS} FROM mapping_reports WHERE {where} {tail}"),  # noqa: S608
                params,
            ).all()
        return [_report(r) for r in rows]

    def find(self, concept: str, api: str, field: str | None, limit: int) -> list[MappingReport]:
        where = "concept = :c AND api = :a" + (" AND field_key = :f" if field else "")
        return self._reports(
            where,
            {"c": concept, "a": api, "f": field_key(field or ""), "n": limit},
            "ORDER BY report_count DESC, updated_at DESC LIMIT :n",
        )

    def by_key(self, concept: str, api: str, field: str, kind: str) -> MappingReport | None:
        rows = self._reports(
            "concept = :c AND api = :a AND field_key = :f AND kind = :k",
            {"c": concept, "a": api, "f": field_key(field), "k": kind},
            "ORDER BY created_at LIMIT 1",
        )
        return rows[0] if rows else None

    def add(self, report: MappingReport, field: str) -> None:
        cols = _COLS + ", field_key"
        values = ", ".join(
            "CAST(:suggestion AS jsonb)" if c.strip() == "suggestion" else f":{c.strip()}"
            for c in cols.split(",")
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO mapping_reports ({cols}) VALUES ({values})"),  # noqa: S608
                _params(report),
            )

    def add_note(self, note: ReportNote) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO mapping_report_notes (note_id, report_id, kind, text, "
                    "created_at, client_name, session_hash, build_id, redactions) VALUES (:i, "
                    ":r, :k, :t, :c, :cl, :s, :b, :red)"
                ),
                {
                    "i": note.note_id,
                    "r": note.report_id,
                    "k": note.kind,
                    "t": note.text,
                    "c": note.created_at,
                    "cl": note.client_name,
                    "s": note.session_hash,
                    "b": note.build_id,
                    "red": note.redactions,
                },
            )
            conn.execute(
                text(
                    "UPDATE mapping_reports SET note_count = note_count + 1, "
                    "report_count = report_count + 1, updated_at = :c WHERE report_id = :r"
                ),
                {"c": note.created_at, "r": note.report_id},
            )

    def get(self, report_id: str) -> MappingReport | None:
        rows = self._reports("report_id = :r", {"r": report_id})
        return rows[0] if rows else None

    def notes(self, report_id: str) -> list[ReportNote]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT note_id, report_id, kind, text, created_at, client_name, "
                    "session_hash, build_id, redactions FROM mapping_report_notes "
                    "WHERE report_id = :r ORDER BY created_at, note_id"
                ),
                {"r": report_id},
            ).all()
        return [
            ReportNote(
                note_id=n.note_id,
                report_id=n.report_id,
                text=n.text,
                created_at=n.created_at,
                kind=n.kind,
                client_name=n.client_name,
                session_hash=n.session_hash,
                build_id=n.build_id,
                redactions=n.redactions,
            )
            for n in rows
        ]

    def list_reports(
        self,
        api: str | None,
        concept: str | None,
        status: MappingStatus | None,
        kind: str | None,
    ) -> list[MappingReport]:
        where, params = ["TRUE"], {}
        for col, value in (
            ("api", api),
            ("concept", concept),
            ("status", status.value if status else None),
            ("kind", kind),
        ):
            if value is not None:
                where.append(f"{col} = :{col}")
                params[col] = value
        return self._reports(
            " AND ".join(where), params, "ORDER BY report_count DESC, updated_at DESC, report_id"
        )

    def save(self, report: MappingReport) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE mapping_reports SET status = :status, reason = :reason, "
                    "route = :route, suggestion = CAST(:suggestion AS jsonb), "
                    "suggestion_status = :suggestion_status, validator_reason = "
                    ":validator_reason, build_id = :build_id, updated_at = :updated_at "
                    "WHERE report_id = :report_id"
                ),
                _params(report),
            )

    def writes_since(self, session_hash: str | None, since: datetime) -> int:
        cond = "session_hash = :h" if session_hash is not None else "session_hash IS NULL"
        with self._engine.connect() as conn:
            n = conn.execute(
                text(
                    f"SELECT (SELECT count(*) FROM mapping_reports WHERE {cond} "  # noqa: S608
                    "AND created_at >= :t) + (SELECT count(*) FROM mapping_report_notes "
                    f"WHERE {cond} AND created_at >= :t)"
                ),
                {"h": session_hash, "t": since},
            ).scalar_one()
        return int(n)

    def purge_open(self, before: datetime) -> int:
        with self._engine.begin() as conn:
            r = conn.execute(
                text("DELETE FROM mapping_reports WHERE status = 'open' AND updated_at < :t"),
                {"t": before},
            )
            return int(r.rowcount or 0)

    def verified(
        self, concept: str | None, api: str | None, status: str | None = None
    ) -> list[VerifiedMapping]:
        where, params = ["TRUE"], {}
        for col, value in (("concept", concept), ("api", api), ("status", status)):
            if value is not None:
                where.append(f"{col} = :{col}")
                params[col] = value
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_VCOLS} FROM verified_mappings WHERE {' AND '.join(where)} "  # noqa: S608
                    "ORDER BY concept, api, canonical_field"
                ),
                params,
            ).all()
        return [_verified(r) for r in rows]

    def put_verified(self, mapping: VerifiedMapping) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO verified_mappings ({_VCOLS}, field_key) VALUES (:mapping_id, "  # noqa: S608
                    ":concept, :canonical_field, :api, CAST(:suggestion AS jsonb), :build_id, "
                    ":report_id, :status, :suspended_reason, :accepted_at, :revalidated_at, "
                    ":field_key) ON CONFLICT (concept, field_key, api) DO UPDATE SET "
                    "mapping_id = EXCLUDED.mapping_id, canonical_field = "
                    "EXCLUDED.canonical_field, suggestion = EXCLUDED.suggestion, "
                    "build_id = EXCLUDED.build_id, report_id = EXCLUDED.report_id, "
                    "status = EXCLUDED.status, suspended_reason = EXCLUDED.suspended_reason, "
                    "accepted_at = EXCLUDED.accepted_at, revalidated_at = EXCLUDED.revalidated_at"
                ),
                {
                    "mapping_id": mapping.mapping_id,
                    "concept": mapping.concept,
                    "canonical_field": mapping.canonical_field,
                    "api": mapping.api,
                    "suggestion": json.dumps(mapping.suggestion.as_json()),
                    "build_id": mapping.build_id,
                    "report_id": mapping.report_id,
                    "status": mapping.status.value,
                    "suspended_reason": mapping.suspended_reason,
                    "accepted_at": mapping.accepted_at,
                    "revalidated_at": mapping.revalidated_at,
                    "field_key": field_key(mapping.canonical_field),
                },
            )

    def verified_for(self, concept: str, api: str, fields: Sequence[str]) -> list[VerifiedMapping]:
        keys = [field_key(f) for f in fields]
        rows = self.verified(concept, api)
        return [m for m in rows if not keys or field_key(m.canonical_field) in keys]
