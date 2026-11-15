"""Port: binary assets stored with a build (the package's own icon)."""

from collections.abc import Sequence
from typing import Protocol

from plume.domain.knowledge.asset import Asset
from plume.domain.shared.ids import BuildId


class AssetRepo(Protocol):
    def put(self, build_id: BuildId, assets: Sequence[Asset]) -> None: ...

    def get(self, build_id: BuildId, name: str) -> Asset | None: ...

    def list(self, build_id: BuildId) -> list[Asset]: ...
