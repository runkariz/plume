import shutil
from pathlib import Path

import pytest

from plume.application.errors import GateFailedError, NotFoundError, SourcePackageError
from plume.application.jobs.maintainer import JobStateError, job_payload
from plume.application.ports.jobs import JobStatus
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import TagName
from plume.infrastructure.sources.gold_file import JsonGoldSource
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.infrastructure.test_dumps_and_storage import zip_dir

GOLD = Path(__file__).resolve().parents[2] / "fixtures" / "gold"


@pytest.fixture
def stack(tmp_path: Path) -> FakeStack:
    return FakeStack(embedder=WordEmbedder(), gold=JsonGoldSource([GOLD]), data_dir=tmp_path)


def _types(stack: FakeStack, job_id: str) -> list[str]:
    return [p["type"] for _, p in stack.maintainer().events_after(job_id, 0)]


def test_wizard_flow(stack: FakeStack, packages: Path) -> None:
    m = stack.maintainer()
    job = m.upload("catalog.zip", zip_dir(packages / "test-catalog"))
    p = job_payload(job)
    assert p["status"] == "uploaded"
    assert p["package"]["contents"] == {"endpoints": 2, "models": 3, "guides": 2}  # + environments
    assert p["package"]["suggested"] == {
        "apiId": "test-catalog-api", "displayName": "Test Catalog API", "tag": "latest"
    }  # fmt: skip
    assert all(c["status"] != "fail" for c in p["package"]["validation"])

    job = m.review(job.job_id, "test-catalog-api", "Test Catalog", "latest")
    p = job_payload(job)
    assert p["status"] == "reviewed"
    assert p["diff"]["counts"]["new"] == p["plan"]["total"] > 0
    assert p["plan"]["toEmbed"] == p["plan"]["total"]
    assert p["liveBuild"] is None

    job = m.start_build(job.job_id)
    job = m.get(job.job_id)  # inline runner: already finished
    assert job.status is JobStatus.STAGED
    assert job.staged_build is not None
    assert job.eval is not None
    assert job.eval["gate"]["passed"] is True
    types = _types(stack, job.job_id)
    assert types[:2] == ["service", "service"]
    assert {"step", "log", "progress"} <= set(types)
    assert types[-1] == "done"
    steps = [e for _, e in m.events_after(job.job_id, 0) if e["type"] == "step"]
    assert {s["key"] for s in steps} >= {"validate", "chunk", "diff", "embed", "store", "evaluate"}
    assert [s["status"] for s in steps if s["key"] == "evaluate"][-1] == "done"
    assert stack.tags.get(ApiId("test-catalog-api"), TagName("latest")) is None  # staged only

    published = m.publish(job.job_id)
    assert published.status is JobStatus.PUBLISHED
    tag = stack.tags.get(ApiId("test-catalog-api"), TagName("latest"))
    assert tag is not None
    assert tag.build_id.value == job.staged_build
    name, data = m.dump(job.job_id)
    assert name.endswith(".plume.jsonl.gz")
    assert data[:2] == b"\x1f\x8b"
    resumed = m.events_after(job.job_id, 3)
    assert resumed[0][0] == 4


def test_second_upload_reviews_against_live(
    stack: FakeStack, packages: Path, tmp_path: Path
) -> None:
    m = stack.maintainer()
    first = m.upload("a.zip", zip_dir(packages / "test-catalog"))
    m.review(first.job_id, "test-catalog-api", "", "latest")
    m.start_build(first.job_id)
    m.publish(first.job_id)

    copy = tmp_path / "v2"
    shutil.copytree(packages / "test-catalog", copy)
    (copy / "connector" / "models" / "error.schema.json").unlink()
    second = m.upload("b.zip", zip_dir(copy))
    p = job_payload(m.review(second.job_id, "test-catalog-api", "", "latest"))
    assert p["liveBuild"] == m.get(first.job_id).staged_build
    assert p["diff"]["counts"]["removed"] == 1
    assert p["diff"]["items"][0]["change"] == "removed"
    assert p["plan"]["toEmbed"] == 0  # every chunk is cached


def test_gate_failure_blocks_publish(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    m = stack.maintainer()
    good = m.upload("a.zip", zip_dir(packages / "test-catalog"))
    m.review(good.job_id, "test-catalog-api", "", "latest")
    m.start_build(good.job_id)
    m.publish(good.job_id)
    damaged = tmp_path / "damaged"
    shutil.copytree(packages / "test-catalog", damaged)
    shutil.rmtree(damaged / "connector" / "endpoints" / "get-api-v1-orders")
    bad = m.upload("bad.zip", zip_dir(damaged))
    m.review(bad.job_id, "test-catalog-api", "", "latest")
    m.start_build(bad.job_id)
    job = m.get(bad.job_id)
    assert job.status is JobStatus.STAGED
    assert job.eval is not None
    assert job.eval["gate"]["passed"] is False
    tones = {r["key"]: r["tone"] for r in job.eval["metrics"]}
    assert tones["recall_at_k"] == "bad"
    with pytest.raises(GateFailedError):
        m.publish(bad.job_id)
    assert m.discard(bad.job_id).status is JobStatus.DISCARDED


def test_states_and_errors(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    m = stack.maintainer()
    with pytest.raises(SourcePackageError, match=r"\.zip"):
        m.upload("x.tar", b"")
    with pytest.raises(NotFoundError):
        m.get("job-nope")
    broken = m.upload("broken.zip", zip_dir(packages / "test-catalog" / "connector" / "models"))
    assert any(c["status"] == "fail" for c in broken.package["validation"])
    with pytest.raises(JobStateError, match="validation"):
        m.review(broken.job_id, "x", "", "latest")
    job = m.upload("ok.zip", zip_dir(packages / "test-catalog"))
    with pytest.raises(JobStateError):
        m.start_build(job.job_id)  # not reviewed
    with pytest.raises(JobStateError):
        m.publish(job.job_id)
    with pytest.raises(JobStateError):
        m.dump(job.job_id)
    with pytest.raises(SourcePackageError, match="renaming"):
        m.review(job.job_id, "other-api", "", "latest")
    with pytest.raises(SourcePackageError):
        m.review(job.job_id, "test-catalog-api", "", "Bad Tag")


def test_failed_build_is_reported(stack: FakeStack, packages: Path) -> None:
    m = stack.maintainer()
    job = m.upload("a.zip", zip_dir(packages / "test-catalog"))
    m.review(job.job_id, "test-catalog-api", "", "latest")
    stack.embedder.fail_on = "List orders"
    m.start_build(job.job_id)
    failed = m.get(job.job_id)
    assert failed.status is JobStatus.FAILED
    assert failed.error
    last = m.events_after(job.job_id, 0)[-1][1]
    assert last == {"type": "done", "status": "failed", "message": failed.error}
    stack.embedder.fail_on = None
    m.start_build(job.job_id)  # retry from failed
    assert m.get(job.job_id).status is JobStatus.STAGED


def test_restart_recovery(stack: FakeStack, packages: Path) -> None:
    from dataclasses import replace  # noqa: PLC0415

    m = stack.maintainer()
    job = m.upload("a.zip", zip_dir(packages / "test-catalog"))
    m.review(job.job_id, "test-catalog-api", "", "latest")
    stack._jobs.save(replace(m.get(job.job_id), status=JobStatus.BUILDING))
    assert m.recover() == [job.job_id]
    recovered = m.get(job.job_id)
    assert recovered.status is JobStatus.FAILED
    assert recovered.error is not None
    assert "interrupted" in recovered.error
    assert m.events_after(job.job_id, 0)[-1][1]["status"] == "failed"
    assert m.recover() == []
