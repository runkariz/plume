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
    tags: tuple[str, ...] = ()
    real_path: str | None = None  # the package's own path when it fixes the version


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
        tag: str | None = None,
    ) -> tuple[list[DocumentSummary], int]:
        """Documents ordered by kind then id (``query`` filters title/path, case-insensitive;
        ``tag`` keeps documents carrying that package tag)."""
        ...

    def summaries(self, build_id: BuildId, doc_ids: Sequence[str]) -> dict[str, DocumentSummary]:
        """Summaries of the given documents (missing ids are left out)."""
        ...

    def counts(self, build_id: BuildId) -> dict[str, int]:
        """Number of documents per kind, plus ``chunks``."""
        ...


FactKey = tuple[str, str, str, str]  # kind, owner_id, name, location ("" when none): find's order


def fact_key(f: Fact) -> FactKey:
    return (f.kind.value, f.owner_id, f.name, f.location.value if f.location else "")


class QueryTooBroadError(Exception):
    """A reader query ran past its time limit."""


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

    def find_page(
        self,
        build_id: BuildId,
        name: str,
        *,
        kind: FactKind | None = None,
        owner_id: str | None = None,
        resource: str | None = None,
        location: FieldLocation | None = None,
        limit: int,
        after: FactKey | None = None,
    ) -> tuple[list[Fact], int]:
        """One page of ``find`` (at most ``limit`` facts after the key ``after``, in find's
        order) and the total number of matches; bounded in the database, never all rows.
        Raises QueryTooBroadError when the database gives up (statement timeout)."""
        ...

    def for_owner(self, build_id: BuildId, owner_id: str) -> list[Fact]: ...

    def endpoints(self, build_id: BuildId) -> list[Fact]:
        """All endpoint facts of the build."""
        ...

    def field_names(self, build_id: BuildId) -> list[str]:
        """Every distinct field fact name of the build (one query, for bulk existence checks)."""
        ...

    def field_types(self, build_id: BuildId) -> list[tuple[str, str | None]]:
        """Every distinct (field name, type) of the build (one query, for bulk shape checks)."""
        ...

    def incomplete_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> list[str]:
        """Endpoint/model ids in scope whose source is flagged incomplete, sorted."""
        ...

    def bounded_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> dict[str, int]:
        """Endpoint/model ids in scope whose field list stops at a nesting level (the schema
        has more fields than Plume lists) -> that level, sorted by id."""
        ...
