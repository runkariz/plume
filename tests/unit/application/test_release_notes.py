"""Release notes through the load pipeline, the post-release review and the dump."""

import json
import shutil
from pathlib import Path

import pytest

from plume.application.errors import NotFoundError
from plume.application.knowledge.release_notes import QuoteNotVerifiedError, ReleaseStateError
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import TagName
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

API = "test-catalog-api"


def _changed_copy(packages: Path, tmp_path: Path) -> Path:
    """test-catalog with `currency` removed from Order and a new `channel` field."""
    copy = tmp_path / "catalog-v2"
    shutil.copytree(packages / "test-catalog", copy)
    path = copy / "connector" / "models" / "order.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"].pop("currency")
    schema["properties"]["channel"] = {"type": "string", "description": "Sales channel."}
    path.write_text(json.dumps(schema))
    return copy


@pytest.fixture
def two_builds(packages: Path, tmp_path: Path) -> tuple[FakeStack, str, str]:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path / "data")
    first = s.load(str(packages / "test-catalog"))
    second = s.load(str(_changed_copy(packages, tmp_path)))
    return s, first, second


def _latest(s: FakeStack) -> str:
    tag = s.tags.get(ApiId(API), TagName("latest"))
    assert tag is not None
    return tag.build_id.value


def test_notes_are_computed_at_load_and_never_hold_the_publish(
    two_builds: tuple[FakeStack, str, str],
) -> None:
    s, first, second = two_builds
    assert _latest(s) == second  # published as before: nothing blocks
    notes = s.release_notes().get(API, second, full=True)
    assert (notes["from"], notes["to"], notes["review"], notes["tagged"]) == (
        first, second, "pending", True,
    )  # fmt: skip
    ops = {(i["subject"]["fieldPath"], i["op"]) for i in notes["items"]}
    assert {("currency", "removed"), ("channel", "added")} <= ops
    assert all(i["class"] in ("unknown", "suspect") for i in notes["items"])  # no source text
    assert notes["counts"]["breaking"] == 0  # nothing visible to users yet
    light = s.release_notes().get(API, second)
    assert light["items"] == []  # only user-visible items; the rest are in the report
    assert sum(g["count"] for g in light["report"]) == len(notes["items"])
    group = light["report"][0]
    page = s.release_notes().report_group(API, second, group["rule"], 0, 1)
    assert (page["count"], len(page["items"])) == (group["count"], 1)
    assert [n["to"] for n in s.release_notes().summaries(API)] == [second]


def test_rollback_and_roll_forward(two_builds: tuple[FakeStack, str, str]) -> None:
    s, first, second = two_builds
    service = s.release_notes()
    with pytest.raises(ReleaseStateError, match="reason"):
        service.rollback(API, second, "  ")
    moved = service.rollback(API, second, "Order lost currency: extraction bug")
    assert moved == {"tag": "latest", "buildId": first, "previous": second,
                     "review": "rolled_back"}  # fmt: skip
    assert _latest(s) == first
    with pytest.raises(ReleaseStateError, match="already rolled back"):
        service.rollback(API, second, "again")
    kept = service.keep(API, second, "the docs really changed")  # roll forward
    assert (kept["review"], _latest(s)) == ("kept", second)
    assert [d["decision"] for d in kept["decisions"]] == ["rollback", "rollforward"]
    with pytest.raises(ReleaseStateError, match="already kept"):
        service.keep(API, second)
    with pytest.raises(NotFoundError):
        service.get(API, first)  # the first build has no notes (no base)


def test_promote_needs_a_verified_quote_and_can_be_undone(
    two_builds: tuple[FakeStack, str, str],
) -> None:
    s, _, second = two_builds
    service = s.release_notes()
    item = next(i for i in service.get(API, second, full=True)["items"]
                if i["subject"]["fieldPath"] == "channel")  # fmt: skip
    with pytest.raises(QuoteNotVerifiedError):
        service.promote(API, second, item["id"], "an invented quote")
    promoted = service.promote(API, second, item["id"], "Sales channel.")
    assert (promoted["class"], promoted["visibleToUsers"]) == ("confirmed", True)
    assert service.get(API, second)["counts"]["confirmed"] == 1
    back = service.demote(API, second, item["id"])
    assert back["class"] == item["class"]
    assert "promotedAt" not in back
    with pytest.raises(ReleaseStateError):
        service.demote(API, second, item["id"])


def test_issues_text_and_notes_survive_a_dump(
    two_builds: tuple[FakeStack, str, str], tmp_path: Path
) -> None:
    s, first, second = two_builds
    text = s.release_notes().issues(API, second, "text")
    assert f"{first} -> {second}" in text
    assert "`" not in text
    ref = s.export().execute(
        __import__("plume.domain.shared.ids", fromlist=["BuildId"]).BuildId(second)
    )
    dst = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path / "data")
    dst.restore().execute(ref)
    restored = dst.notes_repo.get(second)
    assert restored is not None
    assert restored["items"] == s.notes_repo.get(second)["items"]  # type: ignore[index]
    assert dst.notes_repo.get_meta(second) == s.notes_repo.get_meta(second)
