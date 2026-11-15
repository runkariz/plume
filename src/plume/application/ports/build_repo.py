from typing import Protocol

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build
from plume.domain.shared.ids import BuildId


class BuildRepo(Protocol):
    def get(self, build_id: BuildId) -> Build | None: ...

    def save(self, build: Build) -> None:
        """Insert or update a build, its status and its items."""
        ...

    def list(self, api_id: ApiId) -> list[Build]:
        """Builds of an API, newest first."""
        ...
