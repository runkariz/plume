from collections.abc import Iterable, Mapping
from typing import Protocol

from plume.application.ports.embedder import Vector
from plume.domain.shared.ids import BuildId


class VectorIndex(Protocol):
    def cached(self, model: str, dims: int, embed_hashes: Iterable[str]) -> dict[str, Vector]:
        """Vectors already computed for these embed hashes (keyed by hash)."""
        ...

    def cache(self, model: str, dims: int, vectors: Mapping[str, Vector]) -> None: ...

    def set_vectors(self, build_id: BuildId, vectors: Mapping[str, Vector]) -> None:
        """Attach vectors to chunks of a build (keyed by chunk id)."""
        ...

    def missing(self, build_id: BuildId) -> list[str]:
        """Chunk ids of the build without a vector."""
        ...
