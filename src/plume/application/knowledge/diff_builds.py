"""Use case: what changed between two builds of the same API."""

from plume.application.errors import ApplicationError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.domain.knowledge.diff import BuildDiff, diff_items
from plume.domain.shared.ids import BuildId


class DiffBuilds:
    def __init__(self, builds: BuildRepo) -> None:
        self._builds = builds

    def execute(self, old: BuildId, new: BuildId) -> BuildDiff:
        a, b = require_build(self._builds, old), require_build(self._builds, new)
        if a.api_id != b.api_id:
            raise ApplicationError(f"builds belong to different APIs ({a.api_id}, {b.api_id})")
        return diff_items(a.items, b.items)
