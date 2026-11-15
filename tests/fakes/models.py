import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from plume.application.ports.model_repo import ModelJob, ModelSession
from plume.application.ports.model_set_repo import SetSession
from plume.application.ports.model_writer import (
    ModelWriterError,
    ModelWriterUnavailableError,
    Turn,
)
from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import ModelSnapshot, Visibility


class InMemoryModelRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, ModelSession] = {}
        self.snapshots: dict[str, ModelSnapshot] = {}
        self.owners: dict[str, str | None] = {}  # lineage id -> owner key hash

    def save_session(self, session: ModelSession) -> None:
        if session.session_id in self.sessions:
            raise ValueError("duplicate session")
        self.sessions[session.session_id] = session

    def get_session(self, session_id: str) -> ModelSession | None:
        return self.sessions.get(session_id)

    def save_snapshot(self, snapshot: ModelSnapshot, owner_key_hash: str | None = None) -> bool:
        if snapshot.snapshot_id in self.snapshots:
            return False
        if any(
            s.lineage == snapshot.lineage and s.version == snapshot.version
            for s in self.snapshots.values()
        ):
            return False
        self.snapshots[snapshot.snapshot_id] = snapshot
        if snapshot.lineage == snapshot.snapshot_id:
            self.owners.setdefault(snapshot.snapshot_id, owner_key_hash)
        return True

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None:
        return self.snapshots.get(snapshot_id)

    def list_snapshots(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSnapshot]:
        items = [
            s
            for s in self.snapshots.values()
            if (api is None or api in {i.api for i in s.inputs}) and s.visibility in visibilities
        ]
        return sorted(items, key=lambda s: (-s.created_at.timestamp(), s.snapshot_id))[:limit]

    def lineage(self, lineage_id: str) -> list[ModelSnapshot]:
        return sorted(
            (s for s in self.snapshots.values() if s.lineage == lineage_id),
            key=lambda s: s.version,
        )

    def by_session(self, session_id: str) -> list[ModelSnapshot]:
        return sorted(
            (s for s in self.snapshots.values() if s.session_id == session_id),
            key=lambda s: (-s.created_at.timestamp(), -s.version),
        )

    def set_visibility(
        self, snapshot_id: str, visibility: str, released_at: datetime | None
    ) -> None:
        s = self.snapshots[snapshot_id]
        self.snapshots[snapshot_id] = replace(s, visibility=visibility, released_at=released_at)

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        wanted = set(key_hashes)
        return [lin for lin, h in self.owners.items() if h is not None and h in wanted]


class InMemoryModelJobRepo:
    def __init__(self) -> None:
        self.jobs: dict[str, ModelJob] = {}

    def create(self, job: ModelJob) -> None:
        if job.job_id in self.jobs:
            raise ValueError("duplicate job")
        self.jobs[job.job_id] = job

    def get(self, job_id: str) -> ModelJob | None:
        return self.jobs.get(job_id)

    def save(self, job: ModelJob) -> None:
        self.jobs[job.job_id] = job

    def fail_interrupted(self, message: str) -> list[str]:
        ids = [j.job_id for j in self.jobs.values() if j.status in ("queued", "running")]
        for i in ids:
            self.jobs[i] = replace(self.jobs[i], status="failed", error=message)
        return ids


class ScriptedModelWriter:
    """A fake LLM: returns the scripted replies in order (strings, or objects as JSON) and
    records what it was asked."""

    def __init__(self, replies: Sequence[object] = (), available: bool = True) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, list[Turn]]] = []
        self._available = available

    @property
    def name(self) -> str:
        return "fake:scripted"

    def available(self) -> bool:
        return self._available

    def write(self, system: str, turns: Sequence[Turn]) -> str:
        if not self._available:
            raise ModelWriterUnavailableError("not configured")
        self.calls.append((system, list(turns)))
        if not self.replies:
            raise ModelWriterError("no scripted reply left")
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)


class InMemoryModelSetRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, SetSession] = {}
        self.sets: dict[str, ModelSetSnapshot] = {}
        self.owners: dict[str, str | None] = {}

    def save_session(self, session: SetSession) -> None:
        if session.session_id in self.sessions:
            raise ValueError("duplicate session")
        self.sessions[session.session_id] = session

    def get_session(self, session_id: str) -> SetSession | None:
        return self.sessions.get(session_id)

    def save_set(self, snapshot: ModelSetSnapshot, owner_key_hash: str | None = None) -> bool:
        if snapshot.set_id in self.sets or any(
            s.lineage == snapshot.lineage and s.version == snapshot.version
            for s in self.sets.values()
        ):
            return False
        self.sets[snapshot.set_id] = snapshot
        if snapshot.lineage == snapshot.set_id:
            self.owners.setdefault(snapshot.set_id, owner_key_hash)
        return True

    def get_set(self, set_id: str) -> ModelSetSnapshot | None:
        return self.sets.get(set_id)

    def list_sets(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSetSnapshot]:
        items = [
            s
            for s in self.sets.values()
            if (api is None or api in {i.api for i in s.inputs}) and s.visibility in visibilities
        ]
        return sorted(items, key=lambda s: (-s.created_at.timestamp(), s.set_id))[:limit]

    def lineage(self, lineage_id: str) -> list[ModelSetSnapshot]:
        return sorted(
            (s for s in self.sets.values() if s.lineage == lineage_id), key=lambda s: s.version
        )

    def by_session(self, session_id: str) -> list[ModelSetSnapshot]:
        return sorted(
            (s for s in self.sets.values() if s.session_id == session_id),
            key=lambda s: (-s.created_at.timestamp(), -s.version),
        )

    def set_visibility(self, set_id: str, visibility: str, released_at: datetime | None) -> None:
        s = self.sets[set_id]
        self.sets[set_id] = replace(s, visibility=visibility, released_at=released_at)

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        wanted = set(key_hashes)
        return [lin for lin, h in self.owners.items() if h is not None and h in wanted]

    def sets_using(self, snapshot_id: str) -> list[str]:
        return sorted(
            s.set_id
            for s in self.sets.values()
            if any(m.model_id == snapshot_id for m in s.draft.members)
        )
