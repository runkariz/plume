"""In-memory ``SearchIndex`` and ``FactQuery`` (brute-force cosine; word-overlap text match)."""

import re
from collections.abc import Sequence

from plume.application.ports.embedder import Vector
from plume.application.ports.search_index import ChunkHit, DocumentSummary, FactKey, fact_key
from plume.domain.knowledge.document import (
    FIELDS_BOUNDED_KEY,
    Document,
    DocumentKind,
    FieldLocation,
)
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.ids import BuildId
from tests.fakes.knowledge import InMemoryDocumentRepo, InMemoryFactIndex

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"a", "an", "the", "of", "to", "do", "i", "how", "is", "in", "for", "and", "or"})


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in _WORD.findall(text.lower()) if w not in _STOP}


def _summary(d: Document) -> DocumentSummary:
    return DocumentSummary(
        d.doc_id, d.kind, d.title, d.resource, d.method, d.path, d.deprecated, d.tags,
        d.real_path,
    )  # fmt: skip


class InMemorySearchIndex:
    def __init__(self, documents: InMemoryDocumentRepo) -> None:
        self._docs = documents

    def _hits(
        self, build_id: BuildId, kinds: Sequence[DocumentKind]
    ) -> list[tuple[str, Document, str, str]]:
        docs = self._docs.documents.get(build_id.value, {})
        out = []
        for chunk in self._docs.list_chunks(build_id):
            doc = docs[chunk.doc_id]
            if kinds and doc.kind not in kinds:
                continue
            out.append((chunk.chunk_id, doc, chunk.text, chunk.heading))
        return out

    def dense(
        self, build_id: BuildId, vector: Vector, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        vectors = self._docs.vectors.get(build_id.value, {})
        scored = []
        for cid, doc, text, _ in self._hits(build_id, kinds):
            v = vectors.get(cid)
            if v is None:
                continue
            score = sum(a * b for a, b in zip(vector, v, strict=True))
            scored.append(ChunkHit(cid, doc.doc_id, doc.kind, doc.title, text, score))
        return sorted(scored, key=lambda h: (-h.score, h.chunk_id))[:limit]

    def text(
        self, build_id: BuildId, query: str, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        q = _words(query)
        scored = []
        for cid, doc, text, heading in self._hits(build_id, kinds):
            words = _words(text)
            title_words = _words(heading)
            score = len(q & words) + 2 * len(q & title_words)
            if score:
                scored.append(ChunkHit(cid, doc.doc_id, doc.kind, doc.title, text, float(score)))
        return sorted(scored, key=lambda h: (-h.score, h.chunk_id))[:limit]

    def browse(
        self,
        build_id: BuildId,
        kinds: Sequence[DocumentKind] = (),
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        tag: str | None = None,
    ) -> tuple[list[DocumentSummary], int]:
        docs = [
            d
            for d in self._docs.list_documents(build_id)
            if (not kinds or d.kind in kinds)
            and (tag is None or tag in d.tags)
            and (
                not query
                or any(query.lower() in (x or "").lower() for x in (d.title, d.path, d.doc_id))
            )
        ]
        docs.sort(key=lambda d: (d.kind.value, d.doc_id))
        return [_summary(d) for d in docs[offset : offset + limit]], len(docs)

    def summaries(self, build_id: BuildId, doc_ids: Sequence[str]) -> dict[str, DocumentSummary]:
        docs = self._docs.documents.get(build_id.value, {})
        return {i: _summary(docs[i]) for i in doc_ids if i in docs}

    def counts(self, build_id: BuildId) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self._docs.list_documents(build_id):
            out[d.kind.value] = out.get(d.kind.value, 0) + 1
        out["chunks"] = len(self._docs.list_chunks(build_id))
        models = [d for d in self._docs.list_documents(build_id) if d.kind is DocumentKind.MODEL]
        out["model_shapes"] = len({d.shape or d.doc_id for d in models})
        out["model_names"] = len(
            {d.title.split(" / ")[-1].lower() for d in models if d.resource is not None}
        )
        return out


class InMemoryFactQuery:
    def __init__(self, facts: InMemoryFactIndex, documents: InMemoryDocumentRepo) -> None:
        self._facts = facts
        self._docs = documents

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
        n = name.lower()
        out = [
            f
            for f in self._facts.list_facts(build_id)
            if (f.name.lower() == n or f.name.lower().endswith("." + n))
            and (kind is None or f.kind is kind)
            and (owner_id is None or f.owner_id == owner_id)
            and (resource is None or (f.resource or "").lower() == resource.lower())
            and (location is None or f.location is location)
        ]
        return sorted(
            out,
            key=lambda f: (
                f.kind.value,
                f.owner_id,
                f.name,
                f.location.value if f.location else "",
            ),
        )

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
        rows = self.find(build_id, name, kind=kind, owner_id=owner_id, resource=resource,
                         location=location)  # fmt: skip
        rest = [f for f in rows if after is None or fact_key(f) > after]
        return rest[:limit], len(rows)

    def for_owner(self, build_id: BuildId, owner_id: str) -> list[Fact]:
        return [f for f in self._facts.list_facts(build_id) if f.owner_id == owner_id]

    def field_names(self, build_id: BuildId) -> list[str]:
        return sorted(
            {f.name for f in self._facts.list_facts(build_id) if f.kind is FactKind.FIELD}
        )

    def field_types(self, build_id: BuildId) -> list[tuple[str, str | None]]:
        return sorted(
            {
                (f.name, f.type)
                for f in self._facts.list_facts(build_id)
                if f.kind is FactKind.FIELD
            },
            key=lambda x: (x[0], x[1] or ""),
        )

    def endpoints(self, build_id: BuildId) -> list[Fact]:
        return sorted(
            (f for f in self._facts.list_facts(build_id) if f.kind is FactKind.ENDPOINT),
            key=lambda f: f.name,
        )

    def bounded_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in sorted(self._docs.list_documents(build_id), key=lambda d: d.doc_id):
            level = (d.raw or {}).get(FIELDS_BOUNDED_KEY) if isinstance(d.raw, dict) else None
            if (
                isinstance(level, int)
                and d.kind in (DocumentKind.ENDPOINT, DocumentKind.MODEL)
                and (owner_id is None or d.doc_id == owner_id)
                and (resource is None or (d.resource or "").lower() == resource.lower())
            ):
                out[d.doc_id] = level
        return out

    def incomplete_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> list[str]:
        return sorted(
            d.doc_id
            for d in self._docs.list_documents(build_id)
            if not d.complete
            and d.kind in (DocumentKind.ENDPOINT, DocumentKind.MODEL)
            and (owner_id is None or d.doc_id == owner_id)
            and (resource is None or (d.resource or "").lower() == resource.lower())
        )
