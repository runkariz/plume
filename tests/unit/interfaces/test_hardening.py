"""Security hardening of the public surface (docs/security.md)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from plume.application.jobs.maintainer import job_payload
from plume.application.ports.jobs import JobStatus
from plume.bootstrap.container import Container
from plume.bootstrap.servers import mcp_app
from plume.infrastructure.settings import Settings
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.infrastructure.test_dumps_and_storage import zip_dir
from tests.unit.interfaces.test_http_maintainer import AUTH, _client


@pytest.fixture
def stack(tmp_path: Path) -> FakeStack:
    return FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)


def test_security_headers(stack: FakeStack) -> None:
    r = _client(stack).get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_oversized_bodies_are_refused_before_reading(stack: FakeStack) -> None:
    client = _client(stack)
    big = b"x" * (1024 * 1024 + 1)
    r = client.post("/v1/apis/x/search", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "too_large"
    r = client.post(
        "/v1/packages",
        headers={**AUTH, "content-length": str(300 * 1024 * 1024)},
        content=b"",
    )
    assert r.status_code == 413


def test_client_filename_is_not_a_path(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    job = stack.maintainer().upload("../../evil.zip", zip_dir(packages / "test-catalog"))
    stored = list((tmp_path / "jobs" / job.job_id).iterdir())
    assert sorted(p.name for p in stored) == ["package", "upload.zip"]
    assert not (tmp_path / "evil.zip").exists()
    assert job_payload(job)["package"]["filename"] == "../../evil.zip"  # shown, never used


def test_internal_build_errors_are_not_echoed(stack: FakeStack, packages: Path) -> None:
    m = stack.maintainer()
    job = m.upload("a.zip", zip_dir(packages / "test-catalog"))
    m.review(job.job_id, "test-catalog-api", "", "latest")

    def broken(*_: object) -> object:
        raise RuntimeError('(psycopg) syntax error at "SELECT secret FROM tokens"')

    stack.pipeline = broken  # type: ignore[method-assign,assignment]
    m = stack.maintainer()
    m.start_build(job.job_id)
    failed = m.get(job.job_id)
    assert failed.status is JobStatus.FAILED
    assert failed.error is not None
    assert "SELECT" not in failed.error
    assert "internal error (RuntimeError)" in failed.error


def test_weak_tokens_are_refused() -> None:
    with pytest.raises(ValidationError, match="at least 16"):
        Settings(maintainer_tokens=("short",))
    with pytest.raises(ValidationError):
        Settings(maintainer_tokens=(" padded-token-with-spaces ",))
    ok = Settings(maintainer_tokens=("pl_" + "x" * 20,))
    assert "pl_" not in repr(ok)


def test_unexpected_errors_return_a_bare_500(stack: FakeStack) -> None:
    def boom() -> object:
        raise RuntimeError("password=hunter2 at db:5432")

    stack.overviews = boom  # type: ignore[method-assign,assignment]
    r = TestClient(_client(stack).app, raise_server_exceptions=False).get("/v1/apis")
    assert r.status_code == 500
    assert "hunter2" not in r.text
    assert "Traceback" not in r.text


def test_mcp_is_rate_limited() -> None:
    container = Container(settings=Settings(embedder="hash", reader_rate_limit_per_minute=2))
    with TestClient(mcp_app(container), base_url="http://127.0.0.1:18481") as client:
        body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        headers = {"Accept": "application/json, text/event-stream"}
        codes = [client.post("/mcp", json=body, headers=headers).status_code for _ in range(3)]
    assert codes[-1] == 429
    assert all(c != 429 for c in codes[:2])
