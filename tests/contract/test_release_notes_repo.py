"""ReleaseNotesRepo: fake and Postgres alike."""

import pytest

from plume.application.ports.release_notes_repo import ReleaseNotesRepo
from plume.infrastructure.db.repos.release_notes_repo import PostgresReleaseNotesRepo
from tests.contract.conftest import Store
from tests.fakes.models import InMemoryReleaseNotesRepo


@pytest.fixture
def repo(store: Store, request: pytest.FixtureRequest) -> ReleaseNotesRepo:
    if store.kind == "fake":
        return InMemoryReleaseNotesRepo()
    return PostgresReleaseNotesRepo(request.getfixturevalue("clean_engine"))


def _notes(to: str, at: str, review: str = "pending") -> dict[str, object]:
    return {"api": "shop", "from": "b-0", "to": to, "computedAt": at, "review": review,
            "items": [{"id": "ch-1", "class": "suspect"}], "decisions": []}  # fmt: skip


def test_notes_and_meta(repo: ReleaseNotesRepo) -> None:
    assert repo.get("b-1") is None
    repo.save(_notes("b-1", "2026-11-16T10:00:00+00:00"))
    repo.save(_notes("b-2", "2026-11-16T11:00:00+00:00"))
    repo.save(_notes("b-1", "2026-11-16T10:00:00+00:00", "kept"))  # replace
    got = repo.get("b-1")
    assert got is not None
    assert (got["review"], got["items"]) == ("kept", [{"id": "ch-1", "class": "suspect"}])
    assert [n["to"] for n in repo.for_api("shop")] == ["b-2", "b-1"]
    assert repo.for_api("other") == []
    assert repo.get_meta("b-1") is None
    repo.save_meta("b-1", {"streamVersion": "1.0", "pageHashes": {"u": "h"}})
    repo.save_meta("b-1", {"streamVersion": "1.1"})
    assert repo.get_meta("b-1") == {"streamVersion": "1.1"}
