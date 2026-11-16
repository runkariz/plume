"""Removing an API: confirm, refusal while official/unreleased models pin it, force retires them."""

import json
from pathlib import Path

import pytest

from plume.application.errors import NotFoundError
from plume.application.knowledge.remove_api import ApiInUseError, RemoveInputError
from plume.domain.knowledge.api import ApiId
from plume.domain.models.snapshot import Visibility
from tests.fakes.stack import REMOVALS, FakeStack

API = "test-catalog-api"
DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"


def _stack(packages: Path) -> tuple[FakeStack, str]:
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    s.load(str(packages / "second-catalog"))
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    session = s.models().start([API, "second-catalog-api"], "Order")
    model = s.models().submit(session.session_id, draft, maintainer=True).snapshot
    return s, model.snapshot_id


def test_remove_needs_confirm_and_refuses_while_pinned(packages: Path) -> None:
    s, model_id = _stack(packages)
    remove = s.remove_api()
    with pytest.raises(RemoveInputError):
        remove.execute(API, "wrong")
    with pytest.raises(NotFoundError):
        remove.execute("nope", "nope")
    with pytest.raises(ApiInUseError) as exc:
        remove.execute(API, API)
    assert [p["id"] for p in exc.value.pinned] == [model_id]
    assert s.apis.get(ApiId(API)) is not None  # nothing removed


def test_force_retires_pinning_models_and_removes_everything(packages: Path) -> None:
    s, model_id = _stack(packages)
    s.api_display().set(API, "Catalog")
    out = s.remove_api().execute(API, API, force=True, reason="test")
    retired = out["retired"][0]
    expected = {Visibility.OFFICIAL: Visibility.SUPERSEDED,
                Visibility.UNRELEASED: Visibility.DISCARDED}[retired["visibility"]]  # fmt: skip
    assert retired["now"] == expected
    snap = s.models_repo.get_snapshot(model_id)
    assert snap is not None
    assert snap.visibility in (Visibility.SUPERSEDED, Visibility.DISCARDED)
    assert out["removed"]["builds"] == 1
    assert out["removed"]["displayName"] == 1
    assert s.apis.get(ApiId(API)) is None
    assert not [b for b in s.builds.builds.values() if b.api_id.value == API]
    assert s.apis.get(ApiId("second-catalog-api")) is not None  # the other API is untouched
    assert REMOVALS[-1]["api"] == API
    assert REMOVALS[-1]["forced"] is True
