from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from plume.domain.reports.report import Report, ReportNote, ReportStatus
from plume.infrastructure.db.repos._codec import vector_literal

_REPORT_COLS = (
    "report_id, api, build_id, question, what_was_tried, what_was_missing, status, reason, "
    "report_count, note_count, created_at, updated_at, client_name, session_hash, redactions"
)


def _report(r: Any) -> Report:
    return Report(
        report_id=r.report_id, api=r.api, build_id=r.build_id, question=r.question,
        what_was_tried=r.what_was_tried, what_was_missing=r.what_was_missing,
        status=ReportStatus(r.status), reason=r.reason, report_count=r.report_count,
        note_count=r.note_count, created_at=r.created_at, updated_at=r.updated_at,
        client_name=r.client_name, session_hash=r.session_hash, redactions=r.redactions,
    )  # fmt: skip


class PostgresReportRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def similar(
        self, api: str, vector: Sequence[float], model: str, limit: int
    ) -> list[tuple[Report, float]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_REPORT_COLS}, 1 - (embedding <=> CAST(:v AS halfvec)) AS score "  # noqa: S608
                    "FROM reported_questions WHERE api = :a AND embed_model = :m "
                    "AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:v AS halfvec), report_id LIMIT :n"
                ),
                {"v": vector_literal(vector), "a": api, "m": model, "n": limit},
            ).all()
        return [(_report(r), float(r.score)) for r in rows]

    def by_key(self, api: str, key: str) -> Report | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text(
                    f"SELECT {_REPORT_COLS} FROM reported_questions "  # noqa: S608
                    "WHERE api = :a AND duplicate_key = :k ORDER BY created_at LIMIT 1"
                ),
                {"a": api, "k": key},
            ).first()
        return _report(r) if r else None

    def add(self, report: Report, key: str, vector: Sequence[float] | None, model: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO reported_questions ({_REPORT_COLS}, duplicate_key, "  # noqa: S608
                    "embed_model, embedding) VALUES (:report_id, :api, :build_id, :question, "
                    ":what_was_tried, :what_was_missing, :status, :reason, :report_count, "
                    ":note_count, :created_at, :updated_at, :client_name, :session_hash, "
                    ":redactions, :key, :model, CAST(:v AS halfvec))"
                ),
                {
                    "report_id": report.report_id,
                    "api": report.api,
                    "build_id": report.build_id,
                    "question": report.question,
                    "what_was_tried": report.what_was_tried,
                    "what_was_missing": report.what_was_missing,
                    "status": report.status.value,
                    "reason": report.reason,
                    "report_count": report.report_count,
                    "note_count": report.note_count,
                    "created_at": report.created_at,
                    "updated_at": report.updated_at,
                    "client_name": report.client_name,
                    "session_hash": report.session_hash,
                    "redactions": report.redactions,
                    "key": key,
                    "model": model if vector is not None else None,
                    "v": vector_literal(vector) if vector is not None else None,
                },
            )

    def add_note(self, note: ReportNote) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO report_notes (note_id, report_id, kind, text, created_at, "
                    "client_name, session_hash, build_id, redactions) VALUES (:i, :r, :k, :t, "
                    ":c, :cl, :s, :b, :red)"
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
                    "UPDATE reported_questions SET note_count = note_count + 1, "
                    "report_count = report_count + 1, updated_at = :c WHERE report_id = :r"
                ),
                {"c": note.created_at, "r": note.report_id},
            )

    def get(self, report_id: str) -> Report | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text(f"SELECT {_REPORT_COLS} FROM reported_questions WHERE report_id = :r"),  # noqa: S608
                {"r": report_id},
            ).first()
        return _report(r) if r else None

    def notes(self, report_id: str) -> list[ReportNote]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT note_id, report_id, kind, text, created_at, client_name, "
                    "session_hash, build_id, redactions FROM report_notes "
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

    def list(
        self, api: str | None, status: ReportStatus | None, since: datetime | None
    ) -> Iterator[Report]:
        sql = f"SELECT {_REPORT_COLS} FROM reported_questions WHERE TRUE"  # noqa: S608
        params: dict[str, Any] = {}
        if api is not None:
            sql += " AND api = :a"
            params["a"] = api
        if status is not None:
            sql += " AND status = :s"
            params["s"] = status.value
        if since is not None:
            sql += " AND updated_at >= :t"
            params["t"] = since
        sql += " ORDER BY report_count DESC, updated_at DESC, report_id"
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).all()
        yield from (_report(r) for r in rows)

    def set_status(
        self, report_id: str, status: ReportStatus, reason: str | None, at: datetime
    ) -> bool:
        with self._engine.begin() as conn:
            r = conn.execute(
                text(
                    "UPDATE reported_questions SET status = :s, reason = :why, updated_at = :t "
                    "WHERE report_id = :r"
                ),
                {"s": status.value, "why": reason, "t": at, "r": report_id},
            )
            return bool(r.rowcount)

    def writes_since(self, session_hash: str | None, since: datetime) -> int:
        cond = "session_hash = :h" if session_hash is not None else "session_hash IS NULL"
        with self._engine.connect() as conn:
            n = conn.execute(
                text(
                    f"SELECT (SELECT count(*) FROM reported_questions WHERE {cond} "  # noqa: S608
                    "AND created_at >= :t) + (SELECT count(*) FROM report_notes WHERE "
                    f"{cond} AND created_at >= :t)"
                ),
                {"h": session_hash, "t": since},
            ).scalar_one()
        return int(n)

    def purge_open(self, before: datetime) -> int:
        with self._engine.begin() as conn:
            r = conn.execute(
                text("DELETE FROM reported_questions WHERE status = 'open' AND updated_at < :t"),
                {"t": before},
            )
            return int(r.rowcount or 0)
