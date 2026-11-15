"""Stable content hashing.

``content_hash`` normalises text before hashing (Unicode NFC, ``\\r\\n``/``\\r`` -> ``\\n``) so the
same document hashes the same on every platform. ``digest_of_items`` hashes a set of
``(item id, content hash)`` pairs independent of insertion order; it is a build's content hash.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from plume.domain.shared.errors import InvalidIdentifierError

_ALGORITHM = "sha256"
_HASH = re.compile(rf"^{_ALGORITHM}:[0-9a-f]{{64}}$")


@dataclass(frozen=True, slots=True, order=True)
class ContentHash:
    """A ``sha256:<hex>`` digest."""

    value: str

    def __post_init__(self) -> None:
        if not _HASH.fullmatch(self.value):
            raise InvalidIdentifierError(f"invalid content hash: {self.value!r}")

    @property
    def hex(self) -> str:
        return self.value.split(":", 1)[1]

    def short(self, length: int = 12) -> str:
        return self.hex[:length]

    def __str__(self) -> str:
        return self.value


def normalize_text(text: str) -> str:
    """Canonical form used for hashing: NFC and ``\\n`` line endings."""
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _digest(data: bytes) -> ContentHash:
    return ContentHash(f"{_ALGORITHM}:{hashlib.sha256(data).hexdigest()}")


def content_hash(text: str) -> ContentHash:
    """Hash of a text after normalisation."""
    return _digest(normalize_text(text).encode("utf-8"))


def digest_of_items(items: Iterable[tuple[str, ContentHash]]) -> ContentHash:
    """Order-independent digest of ``(item id, content hash)`` pairs. Item ids must be unique."""
    pairs = sorted(items)
    ids = [item_id for item_id, _ in pairs]
    if len(ids) != len(set(ids)):
        raise InvalidIdentifierError("duplicate item ids in digest input")
    lines = "".join(f"{item_id}\0{digest.value}\n" for item_id, digest in pairs)
    return _digest(lines.encode("utf-8"))
