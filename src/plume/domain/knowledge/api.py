"""API identity."""

import re
from dataclasses import dataclass

from plume.domain.shared.errors import InvalidIdentifierError

_API_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True, slots=True, order=True)
class ApiId:
    """Slug that names one API, e.g. ``shopify``. Lower case, digits and inner dashes; max 64."""

    value: str

    def __post_init__(self) -> None:
        if not _API_ID.fullmatch(self.value):
            raise InvalidIdentifierError(f"invalid api id: {self.value!r}")

    def __str__(self) -> str:
        return self.value
