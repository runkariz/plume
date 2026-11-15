"""Use case: embed the chunks of a build that have no vector yet, reusing cached vectors."""

import math
from collections.abc import Callable

from plume.application.dto import EmbedResult
from plume.application.errors import EmbeddingError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.embedder import Embedder, Vector
from plume.application.ports.vector_index import VectorIndex
from plume.domain.shared.ids import BuildId

ProgressCallback = Callable[[int, int], None]


def _check(vector: Vector, dims: int) -> Vector:
    if len(vector) != dims:
        raise EmbeddingError(f"embedder returned {len(vector)} dims, expected {dims}")
    norm = math.sqrt(sum(x * x for x in vector))
    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingError("embedder returned a zero or non-finite vector")
    return vector


class EmbedBuild:
    def __init__(
        self,
        builds: BuildRepo,
        documents: DocumentRepo,
        vectors: VectorIndex,
        embedder: Embedder,
        batch_size: int = 64,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._builds = builds
        self._documents = documents
        self._vectors = vectors
        self._embedder = embedder
        self._batch_size = batch_size

    def execute(self, build_id: BuildId, progress: ProgressCallback | None = None) -> EmbedResult:
        build = require_build(self._builds, build_id)
        model, dims = self._embedder.model, self._embedder.dims
        if build.spec is not None and (build.spec.embed_model, build.spec.dims) != (model, dims):
            raise EmbeddingError(
                f"build {build_id} expects {build.spec.embed_model}/{build.spec.dims}, "
                f"embedder is {model}/{dims}"
            )
        missing = set(self._vectors.missing(build_id))
        chunks = [c for c in self._documents.list_chunks(build_id) if c.chunk_id in missing]
        if not chunks:
            return EmbedResult(chunks=len(build), from_cache=0, embedded=0)

        by_hash: dict[str, list[str]] = {}
        texts: dict[str, str] = {}
        for chunk in chunks:
            key = chunk.embed_hash.value
            by_hash.setdefault(key, []).append(chunk.chunk_id)
            texts[key] = chunk.embed_text

        cached = self._vectors.cached(model, dims, by_hash)
        from_cache = sum(len(by_hash[h]) for h in cached)
        self._vectors.set_vectors(
            build_id, {cid: v for h, v in cached.items() for cid in by_hash[h]}
        )

        todo = [h for h in by_hash if h not in cached]
        done = 0
        for start in range(0, len(todo), self._batch_size):
            batch = todo[start : start + self._batch_size]
            vectors = self._embedder.embed_documents([texts[h] for h in batch])
            if len(vectors) != len(batch):
                raise EmbeddingError(f"embedder returned {len(vectors)} vectors for {len(batch)}")
            fresh = {h: _check(v, dims) for h, v in zip(batch, vectors, strict=True)}
            self._vectors.cache(model, dims, fresh)
            self._vectors.set_vectors(
                build_id, {cid: v for h, v in fresh.items() for cid in by_hash[h]}
            )
            done += sum(len(by_hash[h]) for h in batch)
            if progress is not None:
                progress(done, len(chunks) - from_cache)
        return EmbedResult(chunks=len(build), from_cache=from_cache, embedded=done)
