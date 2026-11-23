import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from plume.application.ports.collection_repo import Collection
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

    def replace_owner_key(self, lineage_id: str, owner_key_hash: str) -> bool:
        if not self.owners.get(lineage_id):
            return False
        self.owners[lineage_id] = owner_key_hash
        return True

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
        self,
        snapshot_id: str,
        visibility: str,
        released_at: datetime | None,
        release_override: dict[str, Any] | None = None,
    ) -> None:
        s = self.snapshots[snapshot_id]
        self.snapshots[snapshot_id] = replace(
            s,
            visibility=visibility,
            released_at=released_at,
            release_override=release_override or s.release_override,
        )

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        wanted = set(key_hashes)
        return [lin for lin, h in self.owners.items() if h is not None and h in wanted]

    def supersede(self, snapshot_id: str, by: str, at: datetime) -> bool:
        s = self.snapshots.get(snapshot_id)
        if s is None or s.visibility != "official":
            return False
        self.snapshots[snapshot_id] = replace(
            s, visibility="superseded", superseded_by=by, superseded_at=at
        )
        return True


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
        self._last_usage: dict[str, int] | None = None

    @property
    def name(self) -> str:
        return "fake:scripted"

    @property
    def last_usage(self) -> dict[str, int] | None:
        return self._last_usage

    def available(self) -> bool:
        return self._available

    def write(self, system: str, turns: Sequence[Turn]) -> str:
        if not self._available:
            raise ModelWriterUnavailableError("not configured")
        self.calls.append((system, list(turns)))
        if not self.replies:
            raise ModelWriterError("no scripted reply left")
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        prompt = sum(len(t.text) for t in turns) // 4  # a rough, deterministic count
        self._last_usage = {"prompt": prompt, "response": len(text) // 4,
                            "total": prompt + len(text) // 4}  # fmt: skip
        return text


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


class InMemoryCollectionRepo:
    def __init__(self) -> None:
        self.collections: dict[str, Collection] = {}
        self.legacy: dict[str, str] = {}  # key hash -> collection id
        # collection id -> {(kind, lineage): (version id, added at)}
        self.entries: dict[str, dict[tuple[str, str], tuple[str | None, datetime]]] = {}

    def create(
        self, collection_id: str, created_at: datetime, legacy_key_hash: str | None = None
    ) -> None:
        self.collections[collection_id] = Collection(collection_id, created_at)
        self.entries.setdefault(collection_id, {})
        if legacy_key_hash:
            self.legacy[legacy_key_hash] = collection_id

    def get(self, collection_id: str) -> Collection | None:
        return self.collections.get(collection_id)

    def add(
        self,
        collection_id: str,
        kind: str,
        lineage_id: str,
        at: datetime,
        version_id: str | None = None,
    ) -> bool:
        rows = self.entries.setdefault(collection_id, {})
        prior = rows.get((kind, lineage_id))
        if prior is None:
            rows[(kind, lineage_id)] = (version_id, at)
            return True
        if version_id:
            rows[(kind, lineage_id)] = (version_id, prior[1])
        return False

    def items(self, collection_id: str) -> list[tuple[str, str, str | None]]:
        rows = sorted(
            self.entries.get(collection_id, {}).items(), key=lambda r: r[1][1], reverse=True
        )
        return [(k, lin, v) for (k, lin), (v, _) in rows]

    def containing(self, kind: str, lineage_id: str) -> list[str]:
        return [cid for cid, rows in self.entries.items() if (kind, lineage_id) in rows]

    def for_legacy_keys(self, key_hashes: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(self.legacy[h] for h in key_hashes if h in self.legacy))

    def merge(self, into: str, source: str, at: datetime) -> int:
        target = self.entries.setdefault(into, {})
        moved = 0
        for key, (version, _) in self.entries.get(source, {}).items():
            if key not in target:
                target[key] = (version, at)
                moved += 1
            elif target[key][0] is None and version:
                target[key] = (version, target[key][1])
        self.entries[source] = {}
        self.collections[source] = replace(self.collections[source], merged_into=into)
        return moved


class InMemoryReleaseNotesRepo:
    def __init__(self) -> None:
        self.notes: dict[str, dict[str, Any]] = {}
        self.meta: dict[str, dict[str, Any]] = {}

    def save_meta(self, build_id: str, meta: Mapping[str, Any]) -> None:
        self.meta[build_id] = json.loads(json.dumps(dict(meta)))

    def get_meta(self, build_id: str) -> dict[str, Any] | None:
        m = self.meta.get(build_id)
        return json.loads(json.dumps(m)) if m is not None else None

    def save(self, notes: Mapping[str, Any]) -> None:
        self.notes[notes["to"]] = json.loads(json.dumps(dict(notes)))

    def get(self, to_build: str) -> dict[str, Any] | None:
        n = self.notes.get(to_build)
        return json.loads(json.dumps(n)) if n is not None else None

    def card_notes(self, to_builds: list[str]) -> dict[str, dict[str, Any]]:
        return {b: n for b in to_builds if (n := self.get(b)) is not None}

    def for_api(self, api_id: str) -> list[dict[str, Any]]:
        rows = [n for n in self.notes.values() if n["api"] == api_id]
        return [
            json.loads(json.dumps(n))
            for n in sorted(rows, key=lambda n: (n["computedAt"], n["to"]), reverse=True)
        ]
