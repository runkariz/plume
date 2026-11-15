from datetime import UTC, datetime

import pytest

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build, BuildStatus
from plume.domain.shared.errors import (
    BuildSealedError,
    EmptyBuildError,
    InvalidIdentifierError,
    UnknownItemError,
)
from plume.domain.shared.hashing import content_hash, digest_of_items
from plume.domain.shared.ids import BuildId
from tests.unit.domain.conftest import T0, T1


def test_new_build_is_an_empty_draft(shopify: ApiId) -> None:
    build = Build.start(shopify, T0)
    assert build.status is BuildStatus.DRAFT
    assert not build.is_sealed
    assert len(build) == 0
    assert build.content_hash is None
    assert build.sealed_at is None


def test_operations_return_new_values_and_leave_the_original(draft: Build) -> None:
    changed = draft.with_item("guide/auth", content_hash("OAuth"))
    assert len(draft) == 2
    assert len(changed) == 3
    assert changed.build_id == draft.build_id


def test_with_item_replaces_an_existing_item(draft: Build) -> None:
    new = content_hash("GET /products v2")
    assert draft.with_item("endpoint/get-products", new).items["endpoint/get-products"] == new


def test_without_item(draft: Build) -> None:
    assert "model/product" not in draft.without_item("model/product").items
    with pytest.raises(UnknownItemError):
        draft.without_item("model/nope")


def test_items_view_is_read_only(draft: Build) -> None:
    with pytest.raises(TypeError):
        draft.items["x"] = content_hash("x")  # type: ignore[index]


def test_seal_computes_the_content_hash(draft: Build) -> None:
    sealed = draft.seal(T1)
    assert sealed.status is BuildStatus.SEALED
    assert sealed.sealed_at == T1
    assert sealed.content_hash == digest_of_items(draft.items.items())


def test_same_items_same_hash_regardless_of_order(shopify: ApiId) -> None:
    a, b = content_hash("a"), content_hash("b")
    one = Build.start(shopify, T0).with_item("x", a).with_item("y", b).seal(T1)
    two = Build.start(shopify, T0).with_item("y", b).with_item("x", a).seal(T1)
    assert one.content_hash == two.content_hash
    assert one.build_id != two.build_id


def test_sealed_build_rejects_every_change(sealed: Build) -> None:
    with pytest.raises(BuildSealedError):
        sealed.with_item("guide/new", content_hash("new"))
    with pytest.raises(BuildSealedError):
        sealed.without_item("model/product")
    with pytest.raises(BuildSealedError):
        sealed.seal(T1)


def test_sealed_build_attributes_are_frozen(sealed: Build) -> None:
    with pytest.raises(AttributeError):
        sealed.status = BuildStatus.DRAFT  # type: ignore[misc]


def test_empty_build_cannot_be_sealed(shopify: ApiId) -> None:
    with pytest.raises(EmptyBuildError):
        Build.start(shopify, T0).seal(T1)


def test_tampered_sealed_build_is_rejected(sealed: Build) -> None:
    with pytest.raises(ValueError, match="does not match"):
        Build(
            api_id=sealed.api_id,
            build_id=sealed.build_id,
            created_at=sealed.created_at,
            status=BuildStatus.SEALED,
            _items={**sealed.items, "extra": content_hash("x")},
            content_hash=sealed.content_hash,
            sealed_at=sealed.sealed_at,
        )


def test_sealed_status_requires_hash_and_time(shopify: ApiId) -> None:
    with pytest.raises(ValueError, match="exactly when"):
        Build(api_id=shopify, build_id=BuildId.new(), created_at=T0, status=BuildStatus.SEALED)


def test_naive_datetimes_are_refused(shopify: ApiId, draft: Build) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Build.start(shopify, datetime(2026, 11, 15))
    with pytest.raises(ValueError, match="timezone-aware"):
        draft.seal(datetime(2026, 11, 15, 13))


def test_sealed_before_created_is_refused(draft: Build) -> None:
    with pytest.raises(ValueError, match="before created_at"):
        draft.seal(datetime(2026, 11, 14, tzinfo=UTC))


@pytest.mark.parametrize("bad", ["", " x", "a b", "-lead", "x" * 513])
def test_item_ids_are_validated(draft: Build, bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        draft.with_item(bad, content_hash("x"))
