from collections.abc import Sequence
from typing import Protocol

from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document, DocumentKind
from plume.domain.shared.ids import BuildId


class DocumentRepo(Protocol):
    def add_documents(self, build_id: BuildId, documents: Sequence[Document]) -> None:
        """Store documents of a draft build (idempotent: same id replaces)."""
        ...

    def list_documents(self, build_id: BuildId) -> list[Document]:
        """All documents of a build, ordered by id."""
        ...

    def get_document(self, build_id: BuildId, doc_id: str) -> Document | None: ...

    def by_source_ids(
        self, build_id: BuildId, kind: DocumentKind, source_ids: Sequence[str]
    ) -> dict[str, Document]:
        """Documents of one kind keyed by the producer's id (``source_id``); missing ids are
        left out."""
        ...

    def operation_ids(self, build_id: BuildId) -> list[tuple[str, str]]:
        """(request.json specOperationId, endpoint doc id) for the build's endpoints that have
        one, ordered by doc id (a few ms; listing every document costs seconds on a large
        build)."""
        ...

    def model_users(self, build_id: BuildId, model_id: str) -> list[tuple[str, tuple[str, ...]]]:
        """The endpoints and triggers with a field whose type is the model (its ``model_id``:
        a $ref, or stream's x-kariz-model on an inline copy), each with the field locations
        (request places / response / payload), ordered by doc id."""
        ...

    def replace_chunks(self, build_id: BuildId, chunks: Sequence[Chunk]) -> None:
        """Set the build's chunks (drops chunks not in ``chunks``)."""
        ...

    def list_chunks(self, build_id: BuildId) -> list[Chunk]:
        """All chunks of a build, ordered by chunk id."""
        ...
