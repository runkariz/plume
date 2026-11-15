"""Port: model sessions (pinned builds) and immutable model snapshots."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from plume.domain.models.snapshot import ModelSnapshot, PinnedInput


@dataclass(frozen=True, slots=True)
class ModelSession:
    session_id: str
    concept: str
    inputs: tuple[PinnedInput, ...]
    created_at: datetime


class ModelRepo(Protocol):
    def save_session(self, session: ModelSession) -> None: ...

    def get_session(self, session_id: str) -> ModelSession | None: ...

    def save_snapshot(self, snapshot: ModelSnapshot) -> bool:
        """Insert; returns False when a snapshot with that id already exists (unchanged)."""
        ...

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None: ...

    def list_snapshots(self, api: str | None = None, limit: int = 50) -> list[ModelSnapshot]:
        """Newest first; ``api`` filters to snapshots that include that API."""
        ...
