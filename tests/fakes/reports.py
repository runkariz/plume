"""An in-memory report repo (tests)."""

import math
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import datetime

from plume.domain.reports.report import Report, ReportNote, ReportStatus


class InMemoryReports:
    def __init__(self) -> None:
        self.reports: dict[str, Report] = {}
        self.keys: dict[str, str] = {}  # report id -> duplicate key
        self.vectors: dict[str, tuple[str, list[float]]] = {}
        self.all_notes: list[ReportNote] = []

    def similar(
        self, api: str, vector: Sequence[float], model: str, limit: int
    ) -> list[tuple[Report, float]]:
        scored = []
        for rid, (m, v) in self.vectors.items():
            r = self.reports.get(rid)
            if r is None or r.api != api or m != model:
                continue
            dot = sum(a * b for a, b in zip(v, vector, strict=False))
            norm = math.sqrt(sum(a * a for a in v)) * math.sqrt(sum(b * b for b in vector))
            scored.append((r, dot / norm if norm else 0.0))
        return sorted(scored, key=lambda x: -x[1])[:limit]

    def by_key(self, api: str, key: str) -> Report | None:
        return next((r for rid, r in self.reports.items()
                     if r.api == api and self.keys.get(rid) == key), None)  # fmt: skip

    def add(self, report: Report, key: str, vector: Sequence[float] | None, model: str) -> None:
        self.reports[report.report_id] = report
        self.keys[report.report_id] = key
        if vector is not None:
            self.vectors[report.report_id] = (model, list(vector))

    def add_note(self, note: ReportNote) -> None:
        self.all_notes.append(note)
        r = self.reports[note.report_id]
        self.reports[r.report_id] = replace(
            r, note_count=r.note_count + 1, report_count=r.report_count + 1,
            updated_at=note.created_at,
        )  # fmt: skip

    def get(self, report_id: str) -> Report | None:
        return self.reports.get(report_id)

    def notes(self, report_id: str) -> list[ReportNote]:
        return [n for n in self.all_notes if n.report_id == report_id]

    def list(
        self, api: str | None, status: ReportStatus | None, since: datetime | None
    ) -> Iterator[Report]:
        rows = [r for r in self.reports.values() if (api is None or r.api == api)
                and (status is None or r.status == status)
                and (since is None or r.updated_at >= since)]  # fmt: skip
        yield from sorted(rows, key=lambda r: (-r.report_count, -r.updated_at.timestamp()))

    def set_status(
        self, report_id: str, status: ReportStatus, reason: str | None, at: datetime
    ) -> bool:
        r = self.reports.get(report_id)
        if r is None:
            return False
        self.reports[report_id] = replace(r, status=status, reason=reason, updated_at=at)
        return True

    def writes_since(self, session_hash: str | None, since: datetime) -> int:
        reports = sum(1 for r in self.reports.values()
                      if r.session_hash == session_hash and r.created_at >= since)  # fmt: skip
        notes = sum(1 for n in self.all_notes
                    if n.session_hash == session_hash and n.created_at >= since)  # fmt: skip
        return reports + notes

    def purge_open(self, before: datetime) -> int:
        gone = [rid for rid, r in self.reports.items()
                if r.status == ReportStatus.OPEN and r.updated_at < before]  # fmt: skip
        for rid in gone:
            del self.reports[rid]
            self.vectors.pop(rid, None)
            self.keys.pop(rid, None)
        self.all_notes = [n for n in self.all_notes if n.report_id not in gone]
        return len(gone)
