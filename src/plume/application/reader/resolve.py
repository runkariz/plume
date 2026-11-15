"""Resolve ``(api, tag | build)`` to a sealed build."""

from dataclasses import dataclass

from plume.application.errors import NotFoundError
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.api import ApiId, ApiInfo
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.tag import LATEST, TagName
from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.ids import BuildId


@dataclass(frozen=True, slots=True)
class ResolvedBuild:
    api: ApiInfo
    build: Build
    tag: str | None

    @property
    def docs_as_of(self) -> str:
        moment = self.build.sealed_at or self.build.created_at
        return moment.date().isoformat()


class BuildResolver:
    def __init__(self, apis: ApiRepo, builds: BuildRepo, tags: TagRepo) -> None:
        self._apis = apis
        self._builds = builds
        self._tags = tags

    def resolve(self, api: str, version: str | None = None) -> ResolvedBuild:
        """``version`` is a tag name or a build id; default ``latest``."""
        try:
            api_id = ApiId(api)
        except InvalidIdentifierError as exc:
            raise NotFoundError(f"unknown api {api!r}") from exc
        info = self._apis.get(api_id)
        if info is None:
            raise NotFoundError(f"unknown api {api!r}")
        version = version or LATEST
        if version.startswith("b-"):
            try:
                build = self._builds.get(BuildId(version))
            except InvalidIdentifierError as exc:
                raise NotFoundError(f"unknown build {version!r}") from exc
            if build is None or build.api_id != api_id or not build.is_sealed:
                raise NotFoundError(f"no sealed build {version} for {api}")
            return ResolvedBuild(info, build, None)
        try:
            name = TagName(version)
        except InvalidIdentifierError as exc:
            raise NotFoundError(f"unknown tag {version!r}") from exc
        tag = self._tags.get(api_id, name)
        if tag is None:
            raise NotFoundError(f"{api} has no tag {version!r}")
        build = self._builds.get(tag.build_id)
        if build is None:  # pragma: no cover - FK guarantees it
            raise NotFoundError(f"tag {version} points at a missing build")
        return ResolvedBuild(info, build, name.value)
