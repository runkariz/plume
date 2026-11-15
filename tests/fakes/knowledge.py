"""In-memory implementations of the knowledge ports. They define the reference behaviour."""

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta

from plume.application.errors import EmbeddingError
from plume.application.ports.embedder import Vector
from plume.application.ports.eval_repo import EvalRecord
from plume.application.ports.job_events import JobEvent
from plume.domain.knowledge.api import ApiId, ApiInfo
from plume.domain.knowledge.asset import Asset
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document
from plume.domain.knowledge.fact import Fact
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId


class FakeClock:
    def __init__(self, start: datetime | None = None, step: timedelta = timedelta(seconds=1)):
        self._now = start or datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        self._step = step

    def now(self) -> datetime:
        self._now += self._step
        return self._now


class InMemoryApiRepo:
    def __init__(self) -> None:
        self.apis: dict[str, ApiInfo] = {}

    def upsert(self, info: ApiInfo) -> None:
        self.apis[info.api_id.value] = info

    def get(self, api_id: ApiId) -> ApiInfo | None:
        return self.apis.get(api_id.value)

    def list(self) -> list[ApiInfo]:
        return [self.apis[k] for k in sorted(self.apis)]


class InMemoryBuildRepo:
    def __init__(self) -> None:
        self.builds: dict[str, Build] = {}

    def get(self, build_id: BuildId) -> Build | None:
        return self.builds.get(build_id.value)

    def save(self, build: Build) -> None:
        current = self.builds.get(build.build_id.value)
        if current is not None and current.is_sealed:
            if build.is_sealed:
                return
            raise ValueError(f"build {build.build_id} is sealed in storage")
        self.builds[build.build_id.value] = build

    def list(self, api_id: ApiId) -> list[Build]:
        found = [b for b in self.builds.values() if b.api_id == api_id]
        return sorted(found, key=lambda b: (-b.created_at.timestamp(), b.build_id.value))


class InMemoryTagRepo:
    def __init__(self) -> None:
        self.tags: dict[tuple[str, str], Tag] = {}

    def get(self, api_id: ApiId, name: TagName) -> Tag | None:
        return self.tags.get((api_id.value, name.value))

    def set(self, tag: Tag) -> None:
        self.tags[(tag.api_id.value, tag.name.value)] = tag

    def list(self, api_id: ApiId) -> list[Tag]:
        return sorted(
            (t for (a, _), t in self.tags.items() if a == api_id.value), key=lambda t: t.name
        )


class InMemoryDocumentRepo:
    """Documents and chunks; also holds the chunk vectors for ``InMemoryVectorIndex``."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Document]] = {}
        self.chunks: dict[str, dict[str, Chunk]] = {}
        self.vectors: dict[str, dict[str, Vector]] = {}

    def add_documents(self, build_id: BuildId, documents: Sequence[Document]) -> None:
        store = self.documents.setdefault(build_id.value, {})
        for d in documents:
            store[d.doc_id] = d

    def list_documents(self, build_id: BuildId) -> list[Document]:
        store = self.documents.get(build_id.value, {})
        return [store[k] for k in sorted(store)]

    def get_document(self, build_id: BuildId, doc_id: str) -> Document | None:
        return self.documents.get(build_id.value, {}).get(doc_id)

    def replace_chunks(self, build_id: BuildId, chunks: Sequence[Chunk]) -> None:
        old = self.chunks.get(build_id.value, {})
        vectors = self.vectors.setdefault(build_id.value, {})
        new = {c.chunk_id: c for c in chunks}
        for cid in list(vectors):
            if cid not in new or old[cid].embed_hash != new[cid].embed_hash:
                del vectors[cid]
        self.chunks[build_id.value] = new

    def list_chunks(self, build_id: BuildId) -> list[Chunk]:
        store = self.chunks.get(build_id.value, {})
        return [store[k] for k in sorted(store)]


class InMemoryVectorIndex:
    def __init__(self, documents: InMemoryDocumentRepo) -> None:
        self._documents = documents
        self.cache_store: dict[tuple[str, str, int], Vector] = {}

    def cached(self, model: str, dims: int, embed_hashes: Iterable[str]) -> dict[str, Vector]:
        return {
            h: self.cache_store[(h, model, dims)]
            for h in embed_hashes
            if (h, model, dims) in self.cache_store
        }

    def cache(self, model: str, dims: int, vectors: Mapping[str, Vector]) -> None:
        for h, v in vectors.items():
            self.cache_store.setdefault((h, model, dims), v)

    def set_vectors(self, build_id: BuildId, vectors: Mapping[str, Vector]) -> None:
        chunks = self._documents.chunks.get(build_id.value, {})
        store = self._documents.vectors.setdefault(build_id.value, {})
        for cid, v in vectors.items():
            if cid in chunks:
                store[cid] = v

    def vectors_of(self, build_id: BuildId) -> dict[str, Vector]:
        return dict(self._documents.vectors.get(build_id.value, {}))

    def missing(self, build_id: BuildId) -> list[str]:
        chunks = self._documents.chunks.get(build_id.value, {})
        have = self._documents.vectors.get(build_id.value, {})
        return sorted(c for c in chunks if c not in have)


class InMemoryFactIndex:
    def __init__(self) -> None:
        self.facts: dict[str, list[Fact]] = {}

    def replace_facts(self, build_id: BuildId, facts: Sequence[Fact]) -> None:
        self.facts[build_id.value] = list(facts)

    def list_facts(self, build_id: BuildId) -> list[Fact]:
        return sorted(self.facts.get(build_id.value, []), key=lambda f: f.fact_id)


class DeterministicEmbedder:
    """Fake embedder: a vector from the text's sha256 (equal text, equal vector)."""

    def __init__(self, dims: int = 768, model: str = "fake-embed-v1") -> None:
        self._dims = dims
        self._model = model
        self.calls: list[int] = []
        self.fail_on: str | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def dims(self) -> int:
        return self._dims

    def _vector(self, text: str) -> Vector:
        seed = hashlib.sha256(text.encode()).digest()
        raw = [((seed[i % 32] + i) % 17) - 8.0 for i in range(self._dims)]
        raw[0] += 0.5
        norm = math.sqrt(sum(x * x for x in raw))
        return tuple(x / norm for x in raw)

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        self.calls.append(len(texts))
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise EmbeddingError("fake failure")
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> Vector:
        return self._vector(text)


class RecordingEvents:
    def __init__(self) -> None:
        self.events: list[JobEvent] = []

    def emit(self, event: JobEvent) -> None:
        self.events.append(event)

    def steps(self) -> list[tuple[str, str]]:
        return [(e.step, e.status.value) for e in self.events if e.status.value != "progress"]


class WordEmbedder(DeterministicEmbedder):
    """Fake embedder whose vectors share dimensions when texts share words (for ranking tests)."""

    def __init__(self, dims: int = 768) -> None:
        super().__init__(dims, model="fake-words-v1")
        from plume.infrastructure.embeddings.hash_embedder import HashEmbedder  # noqa: PLC0415

        self._inner = HashEmbedder(dims)

    def _vector(self, text: str) -> Vector:
        return self._inner.embed_query(text)


class InMemoryEvalRepo:
    def __init__(self) -> None:
        self.records: dict[str, EvalRecord] = {}

    def save(self, record: EvalRecord) -> None:
        self.records[record.build_id.value] = record

    def get(self, build_id: BuildId) -> EvalRecord | None:
        return self.records.get(build_id.value)


class InMemoryAssetRepo:
    def __init__(self) -> None:
        self.assets: dict[tuple[str, str], Asset] = {}

    def put(self, build_id: BuildId, assets: Sequence[Asset]) -> None:
        for a in assets:
            self.assets[(build_id.value, a.name)] = a

    def get(self, build_id: BuildId, name: str) -> Asset | None:
        return self.assets.get((build_id.value, name))

    def list(self, build_id: BuildId) -> list[Asset]:
        return [a for (b, _), a in sorted(self.assets.items()) if b == build_id.value]
