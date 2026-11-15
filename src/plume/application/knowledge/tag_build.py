"""Use case: point a tag at a sealed build (publish or roll back)."""

from plume.application.dto import TagResult
from plume.application.errors import GateFailedError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.tag_repo import TagRepo
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId


class TagBuild:
    def __init__(self, builds: BuildRepo, tags: TagRepo, evals: EvalRepo | None = None) -> None:
        self._builds = builds
        self._tags = tags
        self._evals = evals

    def execute(self, build_id: BuildId, tag: str, force: bool = False) -> TagResult:
        """Move ``tag`` to the build. A build whose stored eval failed the gate is refused
        unless ``force`` (rollback to a known build is a tag move too)."""
        build = require_build(self._builds, build_id)
        if self._evals is not None and not force:
            record = self._evals.get(build_id)
            if record is not None and not record.passed:
                raise GateFailedError(f"build {build_id} failed its quality gate: {record.message}")
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
