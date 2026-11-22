from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from plume.domain.reports.mapping import MappingReport, MappingStatus, VerifiedMapping
from plume.domain.reports.report import ReportNote


class MappingRepo(Protocol):
    def find(self, concept: str, api: str, field: str | None, limit: int) -> list[MappingReport]:
        """Reports for a concept and API (one canonical field's, by its key, when given)."""
        ...

    def by_key(self, concept: str, api: str, field: str, kind: str) -> MappingReport | None:
        """The report for (concept, api, field key, kind): the dedupe key."""
        ...

    def add(self, report: MappingReport, field: str) -> None: ...

    def add_note(self, note: ReportNote) -> None:
        """Add a note (report_id is the mapping report); counts and updated_at move."""
        ...

    def get(self, report_id: str) -> MappingReport | None: ...

    def notes(self, report_id: str) -> list[ReportNote]: ...

    def list_reports(
        self, api: str | None, concept: str | None, status: MappingStatus | None,
        kind: str | None,
    ) -> list[MappingReport]: ...  # fmt: skip

    def save(self, report: MappingReport) -> None:
        """Replace a report's status / reason / suggestion fields."""
        ...

    def writes_since(self, session_hash: str | None, since: datetime) -> int: ...

    def purge_open(self, before: datetime) -> int: ...

    def verified(
        self, concept: str | None, api: str | None, status: str | None = None
    ) -> list[VerifiedMapping]: ...

    def put_verified(self, mapping: VerifiedMapping) -> None:
        """Insert or replace the verified mapping of (concept, field key, api)."""
        ...

    def verified_for(self, concept: str, api: str, fields: Sequence[str]) -> list[VerifiedMapping]:
        """Active and suspended mappings of these field keys (all fields when empty)."""
        ...
