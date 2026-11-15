"""ModelRepo: fake and Postgres alike; Postgres also refuses UPDATE of a snapshot."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from plume.application.ports.model_repo import ModelRepo, ModelSession
from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, snapshot_id_for
from plume.domain.models.validation import Issue
from plume.infrastructure.db.repos.model_repo import PostgresModelRepo
from tests.contract.conftest import Store
from tests.fakes.models import InMemoryModelRepo

DRAFT = parse_draft(
    json.loads(
        (
            Path(__file__).resolve().parents[1] / "fixtures" / "drafts" / "catalog-order-good.json"
        ).read_text()
    )
)
T = datetime(2026, 11, 15, 12, tzinfo=UTC)
INPUTS = (PinnedInput("test-catalog-api", "b-1"), PinnedInput("second-catalog-api", "b-2"))


@pytest.fixture
def repo(store: Store, request: pytest.FixtureRequest) -> ModelRepo:
    if store.kind == "fake":
        return InMemoryModelRepo()
    return PostgresModelRepo(request.getfixturevalue("clean_engine"))


def _snap(session: str, when: datetime, concept: str = "Order") -> ModelSnapshot:
    return ModelSnapshot(
        snapshot_id_for(INPUTS, concept, DRAFT), session, concept, INPUTS, DRAFT, when, 10
    )


def test_sessions_and_snapshots(repo: ModelRepo) -> None:
    s = ModelSession("s-1", "Order", INPUTS, T)
    repo.save_session(s)
    assert repo.get_session("s-1") == s
    assert repo.get_session("s-x") is None
    snap = _snap("s-1", T)
    assert repo.save_snapshot(snap) is True
    assert repo.save_snapshot(snap) is False
    assert repo.get_snapshot(snap.snapshot_id) == snap
    assert repo.get_snapshot("m-nope") is None
    repo.save_session(ModelSession("s-2", "Product", INPUTS, T))
    later = _snap("s-2", T + timedelta(minutes=1), concept="Product")
    repo.save_snapshot(later)
    assert [m.snapshot_id for m in repo.list_snapshots()] == [later.snapshot_id, snap.snapshot_id]
    assert len(repo.list_snapshots("second-catalog-api", 1)) == 1
    assert repo.list_snapshots("shopify") == []


def test_postgres_snapshots_are_immutable(store: Store, request: pytest.FixtureRequest) -> None:
    if store.kind == "fake":
        pytest.skip("database-level rule")
    engine = request.getfixturevalue("clean_engine")
    repo = PostgresModelRepo(engine)
    repo.save_session(ModelSession("s-1", "Order", INPUTS, T))
    snap = _snap("s-1", T)
    repo.save_snapshot(snap)
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
        conn.execute(
            text("UPDATE model_snapshots SET concept = 'x' WHERE snapshot_id = :s"),
            {"s": snap.snapshot_id},
        )
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
        conn.execute(
            text("UPDATE model_snapshots SET model = '{}'::jsonb, visibility = 'official' "
                 "WHERE snapshot_id = :s"),
            {"s": snap.snapshot_id},
        )  # fmt: skip
    repo.set_visibility(snap.snapshot_id, "discarded", None)  # only visibility may change
    got = repo.get_snapshot(snap.snapshot_id)
    assert got is not None
    assert got.visibility == "discarded"


def test_visibility_lineages_and_owners(repo: ModelRepo) -> None:
    from dataclasses import replace  # noqa: PLC0415

    repo.save_session(ModelSession("s-1", "Order", INPUTS, T, "user", None))
    assert repo.get_session("s-1") == ModelSession("s-1", "Order", INPUTS, T, "user", None)
    v1 = replace(_snap("s-1", T), snapshot_id="u-one", visibility="unlisted", origin="user",
                 content_key="m-abc")  # fmt: skip
    assert repo.save_snapshot(v1, "hash-1") is True
    v2 = replace(v1, snapshot_id="u-two", lineage_id="u-one", version=2, based_on="u-one",
                 created_at=T + timedelta(minutes=1))  # fmt: skip
    assert repo.save_snapshot(v2) is True
    clash = replace(v2, snapshot_id="u-three")  # same lineage version: refused
    assert repo.save_snapshot(clash) is False
    assert repo.get_snapshot("u-three") is None
    assert repo.get_snapshot("u-one") == v1
    assert [s.snapshot_id for s in repo.lineage("u-one")] == ["u-one", "u-two"]
    assert [s.snapshot_id for s in repo.by_session("s-1")] == ["u-two", "u-one"]
    assert repo.lineages_for_owner(["hash-1", "nope"]) == ["u-one"]
    assert repo.lineages_for_owner([]) == []
    assert repo.replace_owner_key("u-one", "hash-2") is True  # a retry's new key
    assert repo.lineages_for_owner(["hash-1"]) == []
    assert repo.lineages_for_owner(["hash-2"]) == ["u-one"]
    assert repo.list_snapshots() == []  # official only by default
    assert [s.snapshot_id for s in repo.list_snapshots(visibilities=("unlisted",))] == [
        "u-two",
        "u-one",
    ]
    repo.save_session(ModelSession("s-2", "Order", INPUTS, T))
    m = replace(_snap("s-2", T), visibility="unreleased")
    repo.save_snapshot(m)
    repo.set_visibility(m.snapshot_id, "official", T)
    got = repo.get_snapshot(m.snapshot_id)
    assert got is not None
    assert (got.visibility, got.released_at) == ("official", T)
    assert [s.snapshot_id for s in repo.list_snapshots()] == [m.snapshot_id]
    assert repo.replace_owner_key(m.snapshot_id, "hash-3") is False  # no owner: stays so
    warned = (Issue("WRITE_ONLY_SOURCE", "status", "shopify", "cites a write"),)
    newer = replace(_snap("s-2", T + timedelta(minutes=5)), snapshot_id="m-newer", warnings=warned)
    assert repo.save_snapshot(newer) is True
    assert repo.get_snapshot("m-newer").warnings == newer.warnings  # type: ignore[union-attr]
    assert repo.supersede(m.snapshot_id, "m-newer", T + timedelta(minutes=6)) is True
    gone = repo.get_snapshot(m.snapshot_id)
    assert gone is not None
    assert (gone.visibility, gone.superseded_by) == ("superseded", "m-newer")
    assert gone.superseded_at is not None
    assert repo.supersede(m.snapshot_id, "m-newer", T) is False  # only official ones


def test_model_jobs(store: Store, request: pytest.FixtureRequest) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from plume.application.ports.model_repo import ModelJob  # noqa: PLC0415
    from plume.infrastructure.db.repos.model_repo import PostgresModelJobRepo  # noqa: PLC0415
    from tests.fakes.models import InMemoryModelJobRepo  # noqa: PLC0415

    jobs = (
        InMemoryModelJobRepo()
        if store.kind == "fake"
        else PostgresModelJobRepo(request.getfixturevalue("clean_engine"))
    )
    job = ModelJob("mj-1", "queued", ("a", "b"), "Order", T, T, "s-1", 0, 3, None, None, "g")
    jobs.create(job)
    assert jobs.get("mj-1") == job
    assert jobs.get("mj-x") is None
    done = replace(job, status="succeeded", round=2, snapshot_id="m-1", updated_at=T)
    jobs.save(done)
    assert jobs.get("mj-1") == done
    jobs.create(replace(job, job_id="mj-2", status="running"))
    assert jobs.fail_interrupted("restart") == ["mj-2"]
    failed = jobs.get("mj-2")
    assert failed is not None
    assert (failed.status, failed.error) == ("failed", "restart")
