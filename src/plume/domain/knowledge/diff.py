"""Diff of two builds by item content hash."""

from collections.abc import Mapping
from dataclasses import dataclass

from plume.domain.shared.hashing import ContentHash


@dataclass(frozen=True, slots=True)
class BuildDiff:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: int

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.changed or self.removed)


def diff_items(old: Mapping[str, ContentHash], new: Mapping[str, ContentHash]) -> BuildDiff:
    added = sorted(k for k in new if k not in old)
    removed = sorted(k for k in old if k not in new)
    common = [k for k in new if k in old]
    changed = sorted(k for k in common if new[k] != old[k])
    return BuildDiff(
        added=tuple(added),
        changed=tuple(changed),
        removed=tuple(removed),
        unchanged=len(common) - len(changed),
    )
