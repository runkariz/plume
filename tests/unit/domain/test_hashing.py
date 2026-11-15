import pytest

from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.hashing import ContentHash, content_hash, digest_of_items


def test_content_hash_is_stable_and_known() -> None:
    # sha256("hello") — a fixed vector so a change of algorithm or encoding is caught.
    assert content_hash("hello").value == (
        "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_line_endings_and_unicode_form_do_not_change_the_hash() -> None:
    assert content_hash("a\r\nb\rc") == content_hash("a\nb\nc")
    assert content_hash("café") == content_hash("café")


def test_different_text_different_hash() -> None:
    assert content_hash("a") != content_hash("b")


def test_digest_of_items_ignores_order() -> None:
    a, b = content_hash("a"), content_hash("b")
    assert digest_of_items([("x", a), ("y", b)]) == digest_of_items([("y", b), ("x", a)])


def test_digest_of_items_depends_on_ids_and_hashes() -> None:
    a, b = content_hash("a"), content_hash("b")
    base = digest_of_items([("x", a), ("y", b)])
    assert digest_of_items([("x", b), ("y", a)]) != base
    assert digest_of_items([("x", a), ("z", b)]) != base


def test_digest_of_items_rejects_duplicate_ids() -> None:
    with pytest.raises(InvalidIdentifierError):
        digest_of_items([("x", content_hash("a")), ("x", content_hash("b"))])


@pytest.mark.parametrize("bad", ["", "sha256:abc", "md5:" + "0" * 64, "sha256:" + "G" * 64])
def test_content_hash_value_is_validated(bad: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        ContentHash(bad)


def test_short_form() -> None:
    digest = content_hash("hello")
    assert digest.short() == "2cf24dba5fb0"
    assert str(digest) == digest.value
