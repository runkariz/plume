"""Use case: point a tag at a sealed build (publish or roll back)."""

from plume.application.dto import TagResult
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId


class TagBuild:
    def __init__(self, builds: BuildRepo, tags: TagRepo) -> None:
        self._builds = builds
        self._tags = tags

    def execute(self, build_id: BuildId, tag: str) -> TagResult:
        build = require_build(self._builds, build_id)
        name = TagName(tag)
        current = self._tags.get(build.api_id, name)
        new = Tag.point(name, build) if current is None else current.move_to(build)
        self._tags.set(new)
        return TagResult(
            api_id=build.api_id,
            tag=name.value,
            build_id=build.build_id,
            previous=current.build_id if current is not None else None,
        )
