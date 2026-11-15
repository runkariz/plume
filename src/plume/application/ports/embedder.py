from collections.abc import Sequence
from typing import Protocol

Vector = tuple[float, ...]


class Embedder(Protocol):
    @property
    def model(self) -> str:
        """Model name, recorded on each build (decides cache hits)."""
        ...

    @property
    def dims(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Unit-length vectors, one per text, same order. Raises ``EmbeddingError``."""
        ...

    def embed_query(self, text: str) -> Vector: ...
