from typing import Protocol

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import Tag, TagName


class TagRepo(Protocol):
    def get(self, api_id: ApiId, name: TagName) -> Tag | None: ...

    def set(self, tag: Tag) -> None:
        """Create the tag or move it (atomic)."""
        ...

    def list(self, api_id: ApiId) -> list[Tag]: ...
