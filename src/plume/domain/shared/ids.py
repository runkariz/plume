"""Identifier value objects shared across the domain."""

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
        return cls(f"b-{uuid.uuid4().hex}")

    def __str__(self) -> str:
        return self.value
