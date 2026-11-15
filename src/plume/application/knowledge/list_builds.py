"""Use cases: list APIs, and an API's builds with the tags that point at them."""

from dataclasses import dataclass

from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.api import ApiId, ApiInfo
from plume.domain.knowledge.build import Build


@dataclass(frozen=True, slots=True)
class BuildView:
    build: Build
    tags: tuple[str, ...]


class ListApis:
    def __init__(self, apis: ApiRepo) -> None:
        self._apis = apis

    def execute(self) -> list[ApiInfo]:
        return self._apis.list()


class ListBuilds:
    def __init__(self, builds: BuildRepo, tags: TagRepo) -> None:
        self._builds = builds
        self._tags = tags

    def execute(self, api_id: ApiId) -> list[BuildView]:
        by_build: dict[str, list[str]] = {}
        for tag in self._tags.list(api_id):
            by_build.setdefault(tag.build_id.value, []).append(tag.name.value)
        return [
            BuildView(b, tuple(sorted(by_build.get(b.build_id.value, []))))
            for b in self._builds.list(api_id)
        ]
