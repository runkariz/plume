"""CollectionRepo ("My models" links): fake and Postgres alike."""

from datetime import UTC, datetime, timedelta

import pytest

from plume.application.ports.collection_repo import CollectionRepo
from plume.infrastructure.db.repos.collection_repo import PostgresCollectionRepo
from tests.contract.conftest import Store
from tests.fakes.models import InMemoryCollectionRepo

T = datetime(2026, 11, 16, 12, tzinfo=UTC)


@pytest.fixture
def repo(store: Store, request: pytest.FixtureRequest) -> CollectionRepo:
    if store.kind == "fake":
        return InMemoryCollectionRepo()
    return PostgresCollectionRepo(request.getfixturevalue("clean_engine"))


def test_collections_items_legacy_keys_and_merge(repo: CollectionRepo) -> None:
    repo.create("c-a", T)
    repo.create("c-b", T, legacy_key_hash="hash-1")
    assert repo.get("c-nope") is None
    got = repo.get("c-a")
    assert got is not None
    assert (got.collection_id, got.merged_into) == ("c-a", None)
    assert repo.add("c-a", "model", "u-1", T, "u-1") is True
    assert repo.add("c-a", "model", "u-1", T, "u-1b") is False  # already in it: version moves
    assert repo.add("c-a", "set", "us-1", T + timedelta(minutes=1)) is True
    assert repo.items("c-a") == [("set", "us-1", None), ("model", "u-1", "u-1b")]
    assert repo.containing("model", "u-1") == ["c-a"]
    assert repo.for_legacy_keys(["hash-1", "nope"]) == ["c-b"]
    assert repo.for_legacy_keys([]) == []
    repo.add("c-b", "model", "u-1", T)
    repo.add("c-b", "model", "u-2", T)
    assert repo.merge("c-a", "c-b", T + timedelta(minutes=2)) == 1  # u-2 is new to c-a
    assert sorted((k, lin) for k, lin, _ in repo.items("c-a")) == [
        ("model", "u-1"), ("model", "u-2"), ("set", "us-1"),
    ]  # fmt: skip
    assert {(k, lin): v for k, lin, v in repo.items("c-a")}[("model", "u-1")] == "u-1b"
    assert repo.items("c-b") == []
    merged = repo.get("c-b")
    assert merged is not None
    assert merged.merged_into == "c-a"
