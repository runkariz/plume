"""Ports for reading a sealed build: ranked search, facts lookup, catalogue stats."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from plume.application.ports.embedder import Vector
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.ids import BuildId


@dataclass(frozen=True, slots=True)
class ChunkHit:
    chunk_id: str
    doc_id: str
    kind: DocumentKind
    title: str
    text: str
    score: float  # dense: cosine similarity (-1..1); text: rank score (>= 0)


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    doc_id: str
    kind: DocumentKind
    title: str
    resource: str | None
    method: str | None
    path: str | None
    deprecated: bool


class SearchIndex(Protocol):
    def dense(
        self, build_id: BuildId, vector: Vector, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        """Chunks nearest to ``vector`` (cosine), best first."""
        ...

    def text(
        self, build_id: BuildId, query: str, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        """Chunks matching ``query`` in full text, best first. Empty when nothing matches."""
        ...

    def browse(
        self,
        build_id: BuildId,
        kinds: Sequence[DocumentKind] = (),
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DocumentSummary], int]:
        """Documents ordered by kind then id (``query`` filters title/path, case-insensitive)."""
        ...

    def summaries(self, build_id: BuildId, doc_ids: Sequence[str]) -> dict[str, DocumentSummary]:
        """Summaries of the given documents (missing ids are left out)."""
        ...

    def counts(self, build_id: BuildId) -> dict[str, int]:
        """Number of documents per kind, plus ``chunks``."""
        ...


class FactQuery(Protocol):
    def find(
        self,
        build_id: BuildId,
        name: str,
        *,
        kind: FactKind | None = None,
        owner_id: str | None = None,
        resource: str | None = None,
        location: FieldLocation | None = None,
    ) -> list[Fact]:
        """Facts whose name equals ``name`` or ends with ``.<name>`` (case-insensitive)."""
        ...

    def for_owner(self, build_id: BuildId, owner_id: str) -> list[Fact]: ...

    def endpoints(self, build_id: BuildId) -> list[Fact]:
        """All endpoint facts of the build."""
        ...

    def incomplete_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> list[str]:
        """Endpoint/model ids in scope whose source is flagged incomplete, sorted."""
        ...
