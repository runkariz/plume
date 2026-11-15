"""Clock interface. The domain never reads the system time; callers pass ``datetime`` values."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time (timezone-aware, UTC)."""

    def now(self) -> datetime: ...
