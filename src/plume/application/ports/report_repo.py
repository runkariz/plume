from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Protocol

from plume.domain.reports.report import Report, ReportNote, ReportStatus


class ReportRepo(Protocol):
    def similar(
        self, api: str, vector: Sequence[float], model: str, limit: int
    ) -> list[tuple[Report, float]]:
        """The API's reports closest to the vector (cosine similarity), best first."""
        ...

    def by_key(self, api: str, key: str) -> Report | None:
        """The API's report whose question has this duplicate key."""
        ...

    def add(self, report: Report, key: str, vector: Sequence[float] | None, model: str) -> None: ...

    def add_note(self, note: ReportNote) -> None:
        """Add a note; the report's note_count / report_count and updated_at move."""
        ...

    def get(self, report_id: str) -> Report | None: ...

    def notes(self, report_id: str) -> list[ReportNote]: ...

    def list(
        self, api: str | None, status: ReportStatus | None, since: datetime | None
    ) -> Iterator[Report]:
        """Most reported first, then the most recently updated."""
        ...

    def set_status(
        self, report_id: str, status: ReportStatus, reason: str | None, at: datetime
    ) -> bool: ...

    def writes_since(self, session_hash: str | None, since: datetime) -> int:
        """Reports and notes written by this session (None: sessionless calls) since then."""
        ...

    def purge_open(self, before: datetime) -> int:
        """Delete open reports untouched since ``before`` (with their notes); how many."""
        ...
