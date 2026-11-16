"""In-memory job repo, event log, build importer."""

import threading
from collections.abc import Sequence
from dataclasses import replace

from plume.application.ports.dump_store import BuildSnapshot
from plume.application.ports.jobs import Job, JobStatus, JsonObj, StoredEvent
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId


class InMemoryJobRepo:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> None:
        with self._lock:
            if job.job_id in self.jobs:
                raise ValueError("duplicate job")
            self.jobs[job.job_id] = job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def save(self, job: Job) -> None:
        with self._lock:
            self.jobs[job.job_id] = replace(job)

    def compare_and_set(self, job_id: str, expected: set[JobStatus], new: Job) -> bool:
        with self._lock:
            cur = self.jobs.get(job_id)
            if cur is None or cur.status not in expected:
                return False
            self.jobs[job_id] = new
            return True

    def fail_interrupted(self, message: str) -> list[str]:
        ids = []
        with self._lock:
            for jid, job in list(self.jobs.items()):
                if job.status is JobStatus.BUILDING:
                    self.jobs[jid] = replace(job, status=JobStatus.FAILED, error=message)
                    ids.append(jid)
        return ids


class InMemoryJobEventLog:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, JsonObj]] = []
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)

    def append(self, job_id: str, payload: JsonObj) -> int:
        with self._changed:
            seq = len(self.events) + 1
            self.events.append((seq, job_id, dict(payload)))
            self._changed.notify_all()
            return seq

    def wait(self, job_id: str, seq: int, timeout: float) -> bool:
        def ready() -> bool:
            return any(j == job_id and s > seq for s, j, _ in self.events)

        with self._changed:
            return self._changed.wait_for(ready, timeout=timeout)

    def after(self, job_id: str, seq: int, limit: int = 500) -> list[StoredEvent]:
        return [StoredEvent(s, p) for s, j, p in self.events if j == job_id and s > seq][:limit]


class InMemoryBuildImporter:
    """Restores into a FakeStack's stores."""

    def __init__(self, stack: "object") -> None:
        self._s = stack

    def exists(self, build_id: BuildId) -> bool:
        return self._s.builds.get(build_id) is not None  # type: ignore[attr-defined]

    def restore(self, snapshot: BuildSnapshot, tags: Sequence[str] = ()) -> None:
        s = self._s
        b = snapshot.build
        if self.exists(b.build_id):
            raise ValueError("exists")
        s.apis.upsert(snapshot.api)  # type: ignore[attr-defined]
        s.builds.builds[b.build_id.value] = b  # type: ignore[attr-defined]
        s.documents.add_documents(b.build_id, snapshot.documents)  # type: ignore[attr-defined]
        s.documents.replace_chunks(b.build_id, snapshot.chunks)  # type: ignore[attr-defined]
        s.vectors.set_vectors(b.build_id, snapshot.vectors)  # type: ignore[attr-defined]
        s.facts.replace_facts(b.build_id, snapshot.facts)  # type: ignore[attr-defined]
        if snapshot.eval is not None:
            s.evals.save(snapshot.eval)  # type: ignore[attr-defined]
        if snapshot.assets:
            s.assets.put(b.build_id, snapshot.assets)  # type: ignore[attr-defined]
        if snapshot.package_meta:
            s.notes_repo.save_meta(b.build_id.value, snapshot.package_meta)  # type: ignore[attr-defined]
        if snapshot.release_notes:
            s.notes_repo.save(snapshot.release_notes)  # type: ignore[attr-defined]
        for name in tags:
            s.tags.set(Tag.point(TagName(name), b))  # type: ignore[attr-defined]
