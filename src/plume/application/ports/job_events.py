from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class EventStatus(StrEnum):
    STARTED = "started"
    PROGRESS = "progress"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JobEvent:
    job_id: str
    step: str
    status: EventStatus
    message: str = ""
    source: str = "plume"
    data: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)


class JobEvents(Protocol):
    def emit(self, event: JobEvent) -> None: ...
