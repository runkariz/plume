"""Port: model sessions (pinned builds), immutable model snapshots in lineages, and model
generation jobs."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, Visibility


@dataclass(frozen=True, slots=True)
class ModelSession:
    session_id: str
    concept: str
    inputs: tuple[PinnedInput, ...]
    created_at: datetime
    origin: str = "maintainer"
    based_on: str | None = None
    aliases: tuple[tuple[str, str], ...] = ()  # (api, the concept's name in that API)

    def name_in(self, api: str) -> str:
        """The name to search the concept under in one API (an accepted alias, or the concept)."""
        return dict(self.aliases).get(api, self.concept)


class ModelRepo(Protocol):
    def save_session(self, session: ModelSession) -> None: ...

    def get_session(self, session_id: str) -> ModelSession | None: ...

    def save_snapshot(self, snapshot: ModelSnapshot, owner_key_hash: str | None = None) -> bool:
        """Insert; returns False when a snapshot with that id (or that lineage version) already
        exists (unchanged). A snapshot that starts a lineage also records its lineage, with the
        hash of its owner key when there is one."""
        ...

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None: ...

    def replace_owner_key(self, lineage_id: str, owner_key_hash: str) -> bool:
        """Give a lineage that has an owner a new owner key hash (a retry whose first response
        was lost). False when the lineage has no owner (maintainer models)."""
        ...

    def list_snapshots(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSnapshot]:
        """Newest first; ``api`` filters to snapshots that include that API."""
        ...

    def lineage(self, lineage_id: str) -> list[ModelSnapshot]:
        """Every version of a lineage, oldest first."""
        ...

    def by_session(self, session_id: str) -> list[ModelSnapshot]:
        """Snapshots submitted in a session, newest first."""
        ...

    def set_visibility(
        self, snapshot_id: str, visibility: str, released_at: datetime | None
    ) -> None: ...

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        """Lineage ids whose owner key hash is one of ``key_hashes``."""
        ...


@dataclass(frozen=True, slots=True)
class ModelJob:
    """A server-side model generation (maintainer). Events go to the job event log."""

    job_id: str
    status: str  # queued | running | succeeded | failed
    apis: tuple[str, ...]
    concept: str
    created_at: datetime
    updated_at: datetime
    session_id: str | None = None
    round: int = 0
    max_rounds: int = 0
    snapshot_id: str | None = None
    error: str | None = None
    generator: str = ""
    usage: dict[str, int] | None = None  # LLM tokens so far: {prompt, response, total, ...}
    extra: dict[str, object] = field(default_factory=dict, compare=False)


class ModelJobRepo(Protocol):
    def create(self, job: ModelJob) -> None: ...

    def get(self, job_id: str) -> ModelJob | None: ...

    def save(self, job: ModelJob) -> None: ...

    def fail_interrupted(self, message: str) -> list[str]:
        """Mark queued/running jobs failed (startup recovery); returns their ids."""
        ...
