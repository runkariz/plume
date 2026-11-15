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
