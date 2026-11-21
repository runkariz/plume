"""An in-memory query log repo (tests)."""

from collections.abc import Iterator, Sequence
from datetime import datetime

from plume.domain.querylog.event import QueryEvent


class InMemoryQueryLog:
    def __init__(self) -> None:
        self.events: list[QueryEvent] = []

    def add_many(self, events: Sequence[QueryEvent]) -> None:
        self.events.extend(events)

    def purge(self, before: datetime) -> int:
        keep = [e for e in self.events if e.occurred_at >= before]
        removed = len(self.events) - len(keep)
        self.events = keep
        return removed

    def export(self, since: datetime | None, api: str | None) -> Iterator[QueryEvent]:
        for e in sorted(self.events, key=lambda e: e.occurred_at):
            if (since is None or e.occurred_at >= since) and (api is None or e.api == api):
                yield e
