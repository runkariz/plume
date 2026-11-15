import pytest

from plume.domain.knowledge.api import ApiId
from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.ids import BuildId


@pytest.mark.parametrize("good", ["shopify", "a", "google-ads", "x1", "a" * 64])
def test_valid_api_ids(good: str) -> None:
    assert str(ApiId(good)) == good


@pytest.mark.parametrize("bad", ["", "Shopify", "-x", "x-", "a_b", "a" * 65, "a b"])
def test_invalid_api_ids(bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        ApiId(bad)


def test_new_build_ids_are_unique_and_valid() -> None:
    a, b = BuildId.new(), BuildId.new()
    assert a != b
    assert BuildId(str(a)) == a


@pytest.mark.parametrize("bad", ["", "b-123", "x-" + "0" * 32, "b-" + "G" * 32])
def test_invalid_build_ids(bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        BuildId(bad)
