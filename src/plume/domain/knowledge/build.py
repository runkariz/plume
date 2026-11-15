"""Build: one immutable snapshot of an API's documentation.

Lifecycle: ``DRAFT`` -> ``SEALED``. A draft collects items (document/chunk ids with their content
hash). Sealing computes the build's content hash over all items and freezes it: every change to
a sealed build raises ``BuildSealedError``. ``Build`` is a frozen value; operations return new
instances.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from plume.domain.knowledge.api import ApiId
from plume.domain.shared.errors import (
    BuildSealedError,
    EmptyBuildError,
    InvalidIdentifierError,
    UnknownItemError,
)
from plume.domain.shared.hashing import ContentHash, digest_of_items
from plume.domain.shared.ids import BuildId

_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")


class BuildStatus(StrEnum):
    DRAFT = "draft"
    SEALED = "sealed"


def _require_aware(moment: datetime, name: str) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _check_item_id(item_id: str) -> None:
    if not _ITEM_ID.fullmatch(item_id):
        raise InvalidIdentifierError(f"invalid item id: {item_id!r}")


@dataclass(frozen=True, slots=True)
class Build:
    api_id: ApiId
    build_id: BuildId
    created_at: datetime
    status: BuildStatus = BuildStatus.DRAFT
    _items: Mapping[str, ContentHash] = field(default_factory=lambda: MappingProxyType({}))
    content_hash: ContentHash | None = None
    sealed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        sealed = self.status is BuildStatus.SEALED
        if sealed != (self.content_hash is not None) or sealed != (self.sealed_at is not None):
            raise ValueError("content_hash and sealed_at are set exactly when the build is sealed")
        if self.sealed_at is not None:
            _require_aware(self.sealed_at, "sealed_at")
            if self.sealed_at < self.created_at:
                raise ValueError("sealed_at is before created_at")
        for item_id in self._items:
            _check_item_id(item_id)
        if self.content_hash is not None and self.content_hash != digest_of_items(
            self._items.items()
        ):
            raise ValueError("content_hash does not match the build's items")
        # Freeze the mapping even when a plain dict was passed in.
        object.__setattr__(self, "_items", MappingProxyType(dict(self._items)))

    # -- construction ---------------------------------------------------------------------------

    @classmethod
    def start(cls, api_id: ApiId, created_at: datetime, build_id: BuildId | None = None) -> "Build":
        """A new, empty draft."""
        return cls(api_id=api_id, build_id=build_id or BuildId.new(), created_at=created_at)

    # -- queries --------------------------------------------------------------------------------

    @property
    def is_sealed(self) -> bool:
        return self.status is BuildStatus.SEALED

    @property
    def items(self) -> Mapping[str, ContentHash]:
        """Read-only view of ``item id -> content hash``."""
        return self._items

    def __len__(self) -> int:
        return len(self._items)

    # -- draft operations -----------------------------------------------------------------------

    def _ensure_draft(self, action: str) -> None:
        if self.is_sealed:
            raise BuildSealedError(f"build {self.build_id} is sealed; cannot {action}")

    def with_item(self, item_id: str, digest: ContentHash) -> "Build":
        """Add or replace an item in a draft."""
        self._ensure_draft("add items")
        _check_item_id(item_id)
        return replace(self, _items={**self._items, item_id: digest})

    def without_item(self, item_id: str) -> "Build":
        """Remove an item from a draft."""
        self._ensure_draft("remove items")
        if item_id not in self._items:
            raise UnknownItemError(item_id)
        return replace(self, _items={k: v for k, v in self._items.items() if k != item_id})

    def seal(self, sealed_at: datetime) -> "Build":
        """Freeze the draft and compute its content hash."""
        self._ensure_draft("seal again")
        if not self._items:
            raise EmptyBuildError(f"build {self.build_id} has no items")
        return replace(
            self,
            status=BuildStatus.SEALED,
            content_hash=digest_of_items(self._items.items()),
            sealed_at=sealed_at,
        )
