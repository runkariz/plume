from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Protocol

from plume.domain.querylog.event import QueryEvent


class QueryLogRepo(Protocol):
    def add_many(self, events: Sequence[QueryEvent]) -> None: ...

    def purge(self, before: datetime) -> int:
        """Delete the events older than ``before``; how many."""
        ...

    def export(self, since: datetime | None, api: str | None) -> Iterator[QueryEvent]:
        """Events in time order, from ``since``, of one API or all."""
        ...
