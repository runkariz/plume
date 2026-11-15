"""EvalRepo, JobRepo, JobEventLog: fakes and Postgres behave alike."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from plume.application.ports.eval_repo import EvalRecord, EvalRepo
from plume.application.ports.jobs import Job, JobEventLog, JobRepo, JobStatus
from plume.domain.eval.metrics import EvalMetrics
from plume.domain.knowledge.api import ApiId, ApiInfo
from plume.domain.knowledge.build import Build
from plume.infrastructure.db.repos.eval_repo import PostgresEvalRepo
from plume.infrastructure.jobs.postgres_jobs import PostgresJobEventLog, PostgresJobRepo
from tests.contract.conftest import Store
from tests.fakes.jobs import InMemoryJobEventLog, InMemoryJobRepo
from tests.fakes.knowledge import InMemoryEvalRepo

T = datetime(2026, 11, 15, 12, tzinfo=UTC)
M = EvalMetrics(0.9, 0.8, 0.7, 1.0, 0, 10, 8, 2)


@pytest.fixture
def evals(store: Store, request: pytest.FixtureRequest) -> EvalRepo:
    if store.kind == "fake":
        return InMemoryEvalRepo()
    return PostgresEvalRepo(request.getfixturevalue("clean_engine"))


@pytest.fixture
def jobs(store: Store, request: pytest.FixtureRequest) -> tuple[JobRepo, JobEventLog]:
    if store.kind == "fake":
        return InMemoryJobRepo(), InMemoryJobEventLog()
    engine: Any = request.getfixturevalue("clean_engine")
    return PostgresJobRepo(engine), PostgresJobEventLog(engine)


def test_eval_save_get_replace(store: Store, evals: EvalRepo) -> None:
    store.apis.upsert(ApiInfo(ApiId("acme"), "Acme"))
    b = Build.start(ApiId("acme"), T)
    store.builds.save(b)
    rec = EvalRecord(b.build_id, ApiId("acme"), "sha256:g", M, True, "ok", None, T,
                     ({"qid": "a", "rank": 1},))  # fmt: skip
    evals.save(rec)
    assert evals.get(b.build_id) == rec
    failed = replace(rec, passed=False, message="no", baseline_build=b.build_id)
    evals.save(failed)
    assert evals.get(b.build_id) == failed
    assert evals.get(Build.start(ApiId("acme"), T).build_id) is None


def test_jobs_and_events(jobs: tuple[JobRepo, JobEventLog]) -> None:
    repo, log = jobs
    job = Job("job-1", JobStatus.UPLOADED, "/p", {"filename": "a.zip", "validation": []})
    repo.create(job)
    got = repo.get("job-1")
    assert got is not None
    assert (got.status, got.package, got.tag, got.diff) == (job.status, job.package, "latest", None)
    reviewed = replace(got, status=JobStatus.REVIEWED, api_id="x", diff={"counts": {"new": 1}})
    repo.save(reviewed)
    assert repo.get("job-1").diff == {"counts": {"new": 1}}  # type: ignore[union-attr]
    building = replace(reviewed, status=JobStatus.BUILDING)
    assert repo.compare_and_set("job-1", {JobStatus.REVIEWED}, building)
    assert not repo.compare_and_set("job-1", {JobStatus.REVIEWED}, building)
    assert not repo.compare_and_set("job-nope", {JobStatus.REVIEWED}, building)
    assert repo.get("job-nope") is None

    s1 = log.append("job-1", {"type": "log", "message": "a"})
    s2 = log.append("job-1", {"type": "done", "status": "staged"})
    assert s2 > s1
    assert [e.payload["type"] for e in log.after("job-1", 0)] == ["log", "done"]
    assert [e.seq for e in log.after("job-1", s1)] == [s2]
    assert log.after("job-1", s2) == []


def test_event_wait_wakes_on_append_and_times_out(jobs: tuple[JobRepo, JobEventLog]) -> None:
    import threading  # noqa: PLC0415
    import time  # noqa: PLC0415

    repo, log = jobs
    repo.create(Job("job-w", JobStatus.BUILDING, "/p", {}))
    repo.create(Job("job-o", JobStatus.BUILDING, "/p", {}))
    start = time.monotonic()
    assert log.wait("job-w", 0, 0.3) is False
    assert time.monotonic() - start >= 0.25

    s1 = log.append("job-w", {"type": "log"})
    assert log.wait("job-w", 0, 5) is True  # already there: immediate

    def later() -> None:
        time.sleep(0.3)
        log.append("job-o", {"type": "log"})  # another job: must not count
        time.sleep(0.3)
        log.append("job-w", {"type": "done"})

    t = threading.Thread(target=later)
    start = time.monotonic()
    t.start()
    assert log.wait("job-w", s1, 10) is True
    waited = time.monotonic() - start
    t.join()
    assert 0.5 <= waited < 5, waited
