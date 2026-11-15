"""Tag: a movable name (``latest``, ``2026-10``) that points at one sealed build of an API.

Publishing moves the tag to a new build; rolling back moves it back. The build itself never changes.
"""

import re
from dataclasses import dataclass, replace

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build
from plume.domain.shared.errors import InvalidIdentifierError, TagTargetError
from plume.domain.shared.ids import BuildId

_TAG_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

LATEST = "latest"


@dataclass(frozen=True, slots=True, order=True)
class TagName:
    value: str

    def __post_init__(self) -> None:
        if not _TAG_NAME.fullmatch(self.value):
            raise InvalidIdentifierError(f"invalid tag name: {self.value!r}")

    def __str__(self) -> str:
        return self.value


def _check_target(api_id: ApiId, build: Build) -> None:
    if build.api_id != api_id:
        raise TagTargetError(f"build {build.build_id} belongs to {build.api_id}, not {api_id}")
    if not build.is_sealed:
        raise TagTargetError(f"build {build.build_id} is a draft; only sealed builds can be tagged")


@dataclass(frozen=True, slots=True)
class Tag:
    api_id: ApiId
    name: TagName
    build_id: BuildId

    @classmethod
    def point(cls, name: TagName, build: Build) -> "Tag":
        """Create a tag on a sealed build."""
        _check_target(build.api_id, build)
        return cls(api_id=build.api_id, name=name, build_id=build.build_id)

    def move_to(self, build: Build) -> "Tag":
        """The same tag, pointing at another sealed build of the same API."""
        _check_target(self.api_id, build)
        return replace(self, build_id=build.build_id)
