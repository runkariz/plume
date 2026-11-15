"""Use case: seal a fully embedded draft."""

from plume.application.errors import IncompleteBuildError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.vector_index import VectorIndex
from plume.domain.knowledge.build import Build
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId


class SealBuild:
    def __init__(self, builds: BuildRepo, vectors: VectorIndex, clock: Clock) -> None:
        self._builds = builds
        self._vectors = vectors
        self._clock = clock

    def execute(self, build_id: BuildId) -> Build:
        build = require_build(self._builds, build_id)
        if build.is_sealed:
            return build
        missing = self._vectors.missing(build_id)
        if missing:
            raise IncompleteBuildError(f"build {build_id}: {len(missing)} chunks have no vector")
        sealed = build.seal(self._clock.now())
        self._builds.save(sealed)
        return sealed
