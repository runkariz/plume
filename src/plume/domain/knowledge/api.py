"""API identity and descriptive info."""

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

    @classmethod
    def from_name(cls, name: str) -> "ApiId":
        """Slug a display name: ``Google Ads`` -> ``google-ads``."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64].strip("-")
        return cls(slug)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Category:
    """Category assigned by the package producer; Plume never decides it."""

    key: str
    reason: str | None = None
    confidence: float | None = None
    bundle_version: int | None = None


@dataclass(frozen=True, slots=True)
class ApiInfo:
    api_id: ApiId
    name: str
    summary: str = ""
    doc_link: str | None = None
    icon_url: str | None = None
    category: Category | None = None
    versions: tuple[str, ...] = ()
    # "package": app.json title/displayName; "derived": from the package's id/name.
    name_source: str = "derived"
    # A maintainer's display name (per API, not per build; survives reloads). Wins over `name`.
    name_override: str | None = None

    @property
    def display_name(self) -> str:
        return self.name_override or self.name

    @property
    def display_source(self) -> str:
        return "override" if self.name_override else self.name_source
