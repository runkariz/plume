"""ModelSetRepo: fake and Postgres alike; Postgres also refuses content updates of a set."""

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from plume.application.ports.model_repo import ModelSession
from plume.application.ports.model_set_repo import ModelSetRepo, SetSession
from plume.domain.models.model_set import ModelSetSnapshot, parse_set_draft
from plume.domain.models.snapshot import ModelSnapshot
from plume.infrastructure.db.repos.model_repo import PostgresModelRepo
from plume.infrastructure.db.repos.model_set_repo import PostgresModelSetRepo
from tests.contract.conftest import Store
from tests.contract.test_model_repo import DRAFT, INPUTS, T
from tests.fakes.models import InMemoryModelRepo, InMemoryModelSetRepo


@pytest.fixture
def repos(store: Store, request: pytest.FixtureRequest) -> tuple[ModelSetRepo, object]:
    if store.kind == "fake":
        return InMemoryModelSetRepo(), InMemoryModelRepo()
    engine = request.getfixturevalue("clean_engine")
    return PostgresModelSetRepo(engine), PostgresModelRepo(engine)


def _member(models: object, sid: str) -> str:
    models.save_session(ModelSession(sid, "Order", INPUTS, T))  # type: ignore[attr-defined]
    snap = ModelSnapshot(f"m-{sid}", sid, "Order", INPUTS, DRAFT, T, 1, visibility="unlisted")
    models.save_snapshot(snap)  # type: ignore[attr-defined]
    return snap.snapshot_id


def _set(set_id: str, model_id: str, **kw: object) -> ModelSetSnapshot:
    draft = parse_set_draft({"name": "Shop", "members": {"Order": model_id}, "relations": []})
    base = ModelSetSnapshot(set_id, "ss-1", INPUTS, draft, T)
    return replace(base, **kw)  # type: ignore[arg-type]


def test_sessions_sets_lineages_and_members(repos: tuple[ModelSetRepo, object]) -> None:
    sets, models = repos
    session = SetSession("ss-1", INPUTS, ("Order",), (("Order", "s-1"),), T, "user", None)
    sets.save_session(session)
    assert sets.get_session("ss-1") == session
    assert sets.get_session("ss-x") is None
    model_id = _member(models, "s-1")
    v1 = _set("us-one", model_id, content_key="ms-abc")
    assert sets.save_set(v1, "hash-1") is True
    assert sets.save_set(v1) is False
    assert sets.get_set("us-one") == v1
    v2 = _set("us-two", model_id, lineage_id="us-one", version=2, based_on="us-one",
              created_at=T + timedelta(minutes=1))  # fmt: skip
    assert sets.save_set(v2) is True
    assert sets.save_set(replace(v2, set_id="us-three")) is False  # same lineage version
    assert [x.set_id for x in sets.lineage("us-one")] == ["us-one", "us-two"]
    assert [x.set_id for x in sets.by_session("ss-1")] == ["us-two", "us-one"]
    assert sets.lineages_for_owner(["hash-1"]) == ["us-one"]
    assert sets.sets_using(model_id) == ["us-one", "us-two"]
    assert sets.list_sets() == []
    assert [x.set_id for x in sets.list_sets(visibilities=("unlisted",))] == ["us-two", "us-one"]
    sets.set_visibility("us-two", "official", T)
    got = sets.get_set("us-two")
    assert got is not None
    assert (got.visibility, got.released_at) == ("official", T)
    assert [x.set_id for x in sets.list_sets(INPUTS[0].api)] == ["us-two"]


def test_postgres_sets_are_immutable(store: Store, request: pytest.FixtureRequest) -> None:
    if store.kind == "fake":
        pytest.skip("database-level rule")
    engine = request.getfixturevalue("clean_engine")
    sets, models = PostgresModelSetRepo(engine), PostgresModelRepo(engine)
    sets.save_session(SetSession("ss-1", INPUTS, ("Order",), (("Order", "s-1"),), T))
    model_id = _member(models, "s-1")
    sets.save_set(_set("us-one", model_id))
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
        conn.execute(text("UPDATE model_sets SET name = 'x' WHERE set_id = 'us-one'"))
    with pytest.raises(DBAPIError):  # members must exist
        sets.save_set(_set("us-two", "m-missing"))
    assert sets.get_set("us-two") is None
