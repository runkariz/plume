"""Collections: the "My models" link. A random id that lists lineages of user models and sets."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

KIND_MODEL = "model"
KIND_SET = "set"


@dataclass(frozen=True, slots=True)
class Collection:
    collection_id: str
    created_at: datetime
    merged_into: str | None = None


class CollectionRepo(Protocol):
    def create(
        self, collection_id: str, created_at: datetime, legacy_key_hash: str | None = None
    ) -> None: ...

    def get(self, collection_id: str) -> Collection | None: ...

    def add(
        self,
        collection_id: str,
        kind: str,
        lineage_id: str,
        at: datetime,
        version_id: str | None = None,
    ) -> bool:
        """Put a lineage in the collection and record ``version_id`` as the newest version
        saved INTO it. False when the lineage was already there (its version is updated)."""
        ...

    def items(self, collection_id: str) -> list[tuple[str, str, str | None]]:
        """(kind, lineage id, newest version saved into it or None), most recent first."""
        ...

    def containing(self, kind: str, lineage_id: str) -> list[str]:
        """Collections that hold this lineage (oldest first)."""
        ...

    def for_legacy_keys(self, key_hashes: Sequence[str]) -> list[str]:
        """Collections migrated from these owner-key hashes."""
        ...

    def merge(self, into: str, source: str, at: datetime) -> int:
        """Move every lineage of ``source`` into ``into`` and mark ``source`` merged; returns how
        many were new to ``into``."""
        ...
