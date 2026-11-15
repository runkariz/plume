import pytest

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.tag import LATEST, Tag, TagName
from plume.domain.shared.errors import InvalidIdentifierError, TagTargetError
from plume.domain.shared.hashing import content_hash
from tests.unit.domain.conftest import T0, T1


def test_tag_points_at_a_sealed_build(sealed: Build) -> None:
    tag = Tag.point(TagName(LATEST), sealed)
    assert tag.build_id == sealed.build_id
    assert tag.api_id == sealed.api_id


def test_draft_cannot_be_tagged(draft: Build) -> None:
    with pytest.raises(TagTargetError, match="draft"):
        Tag.point(TagName(LATEST), draft)


def test_move_and_roll_back(sealed: Build, shopify: ApiId) -> None:
    newer = Build.start(shopify, T0).with_item("x", content_hash("x")).seal(T1)
    tag = Tag.point(TagName(LATEST), sealed)
    moved = tag.move_to(newer)
    assert moved.build_id == newer.build_id
    assert tag.build_id == sealed.build_id  # the old value is unchanged
    assert moved.move_to(sealed) == tag


def test_tag_cannot_move_to_another_api(sealed: Build) -> None:
    other = Build.start(ApiId("stripe"), T0).with_item("x", content_hash("x")).seal(T1)
    with pytest.raises(TagTargetError, match="belongs to"):
        Tag.point(TagName(LATEST), sealed).move_to(other)


def test_tag_cannot_move_to_a_draft(sealed: Build, draft: Build) -> None:
    with pytest.raises(TagTargetError):
        Tag.point(TagName(LATEST), sealed).move_to(draft)


@pytest.mark.parametrize("good", ["latest", "2026-10", "v1.2.3", "stable_1"])
def test_valid_tag_names(good: str) -> None:
    assert str(TagName(good)) == good


@pytest.mark.parametrize("bad", ["", "Latest", "-x", "a b", "x" * 65])
def test_invalid_tag_names(bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        TagName(bad)
