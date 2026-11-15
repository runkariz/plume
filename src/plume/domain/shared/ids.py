"""Identifier value objects shared across the domain."""

import hashlib
import re
import uuid
from dataclasses import dataclass

from plume.domain.shared.errors import InvalidIdentifierError

_BUILD_ID = re.compile(r"^b-[0-9a-f]{32}$")


@dataclass(frozen=True, slots=True)
class BuildId:
    """Identity of one build. Opaque, assigned when the draft is created."""

    value: str

    def __post_init__(self) -> None:
        if not _BUILD_ID.fullmatch(self.value):
            raise InvalidIdentifierError(f"invalid build id: {self.value!r}")

    @classmethod
    def new(cls) -> "BuildId":
        """A random id (for builds that are not derived from a source package)."""
        return cls(f"b-{uuid.uuid4().hex}")

    @classmethod
    def derive(cls, *parts: str) -> "BuildId":
        """A deterministic id: the same inputs always give the same build id."""
        digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
        return cls(f"b-{digest[:32]}")

    def __str__(self) -> str:
        return self.value
