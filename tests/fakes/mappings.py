# ruff: noqa: E501
"""An in-memory mapping report repo (tests)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from plume.domain.reports.mapping import (
    MappingReport,
    MappingStatus,
    VerifiedMapping,
    field_key,
)
from plume.domain.reports.report import ReportNote


class InMemoryMappings:
    def __init__(self) -> None:
        self.reports: dict[str, MappingReport] = {}
        self.all_notes: list[ReportNote] = []
        self.mappings: dict[tuple[str, str, str], VerifiedMapping] = {}

    def find(self, concept: str, api: str, field: str | None, limit: int) -> list[MappingReport]:
        rows = [r for r in self.reports.values() if r.concept == concept and r.api == api
                and (field is None or field_key(r.canonical_field) == field_key(field))]  # fmt: skip
        return sorted(rows, key=lambda r: -r.report_count)[:limit]

    def by_key(self, concept: str, api: str, field: str, kind: str) -> MappingReport | None:
        return next((r for r in self.reports.values() if r.concept == concept and r.api == api
                     and field_key(r.canonical_field) == field_key(field)
                     and r.kind.value == kind), None)  # fmt: skip

    def add(self, report: MappingReport, field: str) -> None:
        self.reports[report.report_id] = report

    def add_note(self, note: ReportNote) -> None:
        self.all_notes.append(note)
        r = self.reports[note.report_id]
        self.reports[r.report_id] = replace(r, note_count=r.note_count + 1,
                                            report_count=r.report_count + 1,
                                            updated_at=note.created_at)  # fmt: skip

    def get(self, report_id: str) -> MappingReport | None:
        return self.reports.get(report_id)

    def notes(self, report_id: str) -> list[ReportNote]:
        return [n for n in self.all_notes if n.report_id == report_id]

    def list_reports(self, api: str | None, concept: str | None, status: MappingStatus | None,
             kind: str | None) -> list[MappingReport]:  # fmt: skip
        rows = [r for r in self.reports.values() if (api is None or r.api == api)
                and (concept is None or r.concept == concept)
                and (status is None or r.status == status)
                and (kind is None or r.kind.value == kind)]  # fmt: skip
        return sorted(rows, key=lambda r: (-r.report_count, -r.updated_at.timestamp()))

    def save(self, report: MappingReport) -> None:
        self.reports[report.report_id] = report

    def writes_since(self, session_hash: str | None, since: datetime) -> int:
        return sum(1 for r in self.reports.values()
                   if r.session_hash == session_hash and r.created_at >= since) + sum(
            1 for n in self.all_notes if n.session_hash == session_hash and n.created_at >= since
        )  # fmt: skip

    def purge_open(self, before: datetime) -> int:
        gone = [k for k, r in self.reports.items()
                if r.status == MappingStatus.OPEN and r.updated_at < before]  # fmt: skip
        for k in gone:
            del self.reports[k]
        self.all_notes = [n for n in self.all_notes if n.report_id not in gone]
        return len(gone)

    def verified(self, concept: str | None, api: str | None,
                 status: str | None = None) -> list[VerifiedMapping]:  # fmt: skip
        return [m for m in self.mappings.values() if (concept is None or m.concept == concept)
                and (api is None or m.api == api)
                and (status is None or m.status.value == status)]  # fmt: skip

    def put_verified(self, mapping: VerifiedMapping) -> None:
        key = (mapping.concept, field_key(mapping.canonical_field), mapping.api)
        self.mappings[key] = mapping

    def verified_for(self, concept: str, api: str, fields: Sequence[str]) -> list[VerifiedMapping]:
        keys = {field_key(f) for f in fields}
        return [m for (c, f, a), m in self.mappings.items()
                if c == concept and a == api and (not keys or f in keys)]  # fmt: skip
