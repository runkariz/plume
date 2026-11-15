"""Port: model set sessions and immutable model set snapshots (lineages, visibility, owners)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import PinnedInput, Visibility


@dataclass(frozen=True, slots=True)
class SetSession:
    session_id: str
    inputs: tuple[PinnedInput, ...]
    concepts: tuple[str, ...]
    member_sessions: tuple[tuple[str, str], ...]  # (concept, model session id)
    created_at: datetime
    origin: str = "user"
    based_on: str | None = None


class ModelSetRepo(Protocol):
    def save_session(self, session: SetSession) -> None: ...

    def get_session(self, session_id: str) -> SetSession | None: ...

    def save_set(self, snapshot: ModelSetSnapshot, owner_key_hash: str | None = None) -> bool:
        """Insert; False when that id (or lineage version) already exists."""
        ...

    def get_set(self, set_id: str) -> ModelSetSnapshot | None: ...

    def list_sets(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSetSnapshot]: ...

    def lineage(self, lineage_id: str) -> list[ModelSetSnapshot]: ...

    def by_session(self, session_id: str) -> list[ModelSetSnapshot]: ...

    def set_visibility(
        self, set_id: str, visibility: str, released_at: datetime | None
    ) -> None: ...

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]: ...

    def sets_using(self, snapshot_id: str) -> list[str]:
        """Ids of the sets that reference a model snapshot."""
        ...
