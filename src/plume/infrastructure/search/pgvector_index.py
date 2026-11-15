from collections.abc import Iterable, Mapping

from sqlalchemy import Engine, text

from plume.application.ports.embedder import Vector
from plume.domain.shared.ids import BuildId
from plume.infrastructure.db.repos._codec import parse_vector, vector_literal


class PgVectorIndex:
    """``VectorIndex`` on pgvector ``halfvec`` columns (chunks.embedding, embed_cache)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def cached(self, model: str, dims: int, embed_hashes: Iterable[str]) -> dict[str, Vector]:
        hashes = list(embed_hashes)
        if not hashes:
            return {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT embed_hash, embedding::text AS v FROM embed_cache "
                    "WHERE model = :m AND dims = :d AND embed_hash = ANY(:h)"
                ),
                {"m": model, "d": dims, "h": hashes},
            ).all()
        return {r.embed_hash: parse_vector(r.v) for r in rows}

    def cache(self, model: str, dims: int, vectors: Mapping[str, Vector]) -> None:
        if not vectors:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO embed_cache (embed_hash, model, dims, embedding) "
                    "VALUES (:h, :m, :d, CAST(:v AS halfvec)) "
                    "ON CONFLICT (embed_hash, model, dims) DO NOTHING"
                ),
                [
                    {"h": h, "m": model, "d": dims, "v": vector_literal(v)}
                    for h, v in vectors.items()
                ],
            )

    def set_vectors(self, build_id: BuildId, vectors: Mapping[str, Vector]) -> None:
        if not vectors:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE chunks SET embedding = CAST(:v AS halfvec) "
                    "WHERE build_id = :b AND chunk_id = :c"
                ),
                [{"b": build_id.value, "c": c, "v": vector_literal(v)} for c, v in vectors.items()],
            )

    def missing(self, build_id: BuildId) -> list[str]:
        with self._engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT chunk_id FROM chunks WHERE build_id = :b AND embedding IS NULL "
                        "ORDER BY chunk_id"
                    ),
                    {"b": build_id.value},
                ).scalars()
            )

    def vectors_of(self, build_id: BuildId) -> dict[str, Vector]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT chunk_id, embedding::text AS v FROM chunks "
                    "WHERE build_id = :b AND embedding IS NOT NULL"
                ),
                {"b": build_id.value},
            ).all()
        return {r.chunk_id: parse_vector(r.v) for r in rows}
