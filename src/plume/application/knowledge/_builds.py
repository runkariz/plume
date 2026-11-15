from plume.application.errors import NotFoundError
from plume.application.ports.build_repo import BuildRepo
from plume.domain.knowledge.build import Build
from plume.domain.shared.ids import BuildId


def require_build(builds: BuildRepo, build_id: BuildId) -> Build:
    build = builds.get(build_id)
    if build is None:
        raise NotFoundError(f"build {build_id} not found")
    return build
