from collections.abc import Sequence
from typing import Protocol

from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document
from plume.domain.shared.ids import BuildId


class DocumentRepo(Protocol):
    def add_documents(self, build_id: BuildId, documents: Sequence[Document]) -> None:
        """Store documents of a draft build (idempotent: same id replaces)."""
        ...

    def list_documents(self, build_id: BuildId) -> list[Document]:
        """All documents of a build, ordered by id."""
        ...

    def get_document(self, build_id: BuildId, doc_id: str) -> Document | None: ...

    def replace_chunks(self, build_id: BuildId, chunks: Sequence[Chunk]) -> None:
        """Set the build's chunks (drops chunks not in ``chunks``)."""
        ...

    def list_chunks(self, build_id: BuildId) -> list[Chunk]:
        """All chunks of a build, ordered by chunk id."""
        ...
