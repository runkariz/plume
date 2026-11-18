"""``SearchIndex`` and ``FactQuery`` on Postgres: pgvector (cosine on halfvec) + tsvector."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.embedder import Vector
from plume.application.ports.search_index import ChunkHit, DocumentSummary
from plume.domain.knowledge.document import FIELDS_BOUNDED_KEY, DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.ids import BuildId
from plume.infrastructure.db.repos._codec import vector_literal
from plume.infrastructure.search.postgres_fact_index import fact_from_row

_KIND_FILTER = " AND (cardinality(CAST(:kinds AS text[])) = 0 OR d.kind = ANY(:kinds))"
_BROWSE_FILTER = (
    "d.build_id = :b"
    + _KIND_FILTER
    + " AND (CAST(:q AS text) IS NULL OR lower(d.title) LIKE :like ESCAPE '\\' "
    "OR lower(coalesce(d.path, '')) LIKE :like ESCAPE '\\' "
    "OR lower(d.doc_id) LIKE :like ESCAPE '\\')"
    " AND (CAST(:tag AS text) IS NULL OR :tag = ANY(d.tags))"
)
# OR-semantics query: every word may match. ts_rank (weights A=title, B=body; normalised by
# log length) favours documents whose title matches over long pages repeating one common word.
_OR_QUERY = "to_tsquery('english', replace(plainto_tsquery('english', :q)::text, ' & ', ' | '))"


def _hit(row: Any) -> ChunkHit:
    return ChunkHit(
        chunk_id=row.chunk_id,
        doc_id=row.doc_id,
        kind=DocumentKind(row.kind),
        title=row.title,
        text=row.text,
        score=float(row.score),
    )


def _summary(row: Any) -> DocumentSummary:
    return DocumentSummary(
        doc_id=row.doc_id,
        kind=DocumentKind(row.kind),
        title=row.title,
        resource=row.resource,
        method=row.method,
        path=row.path,
        deprecated=row.deprecated,
        tags=tuple(getattr(row, "tags", None) or ()),
        real_path=getattr(row, "real_path", None),
    )


def _like(value: str) -> str:
    return value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PostgresSearchIndex:
    def __init__(self, engine: Engine, ef_search: int = 200) -> None:
        self._engine = engine
        self._ef_search = ef_search

    def dense(
        self, build_id: BuildId, vector: Vector, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        with self._engine.begin() as conn:
            # HNSW is shared by all builds; iterative scan keeps the build filter from starving
            # the LIMIT (pgvector >= 0.8).
            conn.execute(text(f"SET LOCAL hnsw.ef_search = {int(self._ef_search)}"))
            conn.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
            rows = conn.execute(
                text(
                    "SELECT c.chunk_id, c.doc_id, d.kind, d.title, c.text, "
                    "1 - (c.embedding <=> CAST(:v AS halfvec)) AS score "
                    "FROM chunks c JOIN documents d USING (build_id, doc_id) "
                    "WHERE c.build_id = :b AND c.embedding IS NOT NULL"
                    + _KIND_FILTER
                    + " ORDER BY c.embedding <=> CAST(:v AS halfvec), c.chunk_id LIMIT :n"
                ),
                {
                    "v": vector_literal(vector),
                    "b": build_id.value,
                    "kinds": [k.value for k in kinds],
                    "n": limit,
                },
            ).all()
        return [_hit(r) for r in rows]

    def text(
        self, build_id: BuildId, query: str, limit: int, kinds: Sequence[DocumentKind] = ()
    ) -> list[ChunkHit]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"WITH q AS (SELECT {_OR_QUERY} AS q) "  # noqa: S608 - constant fragment
                    "SELECT c.chunk_id, c.doc_id, d.kind, d.title, c.text, "
                    "ts_rank(c.tsv, q.q, 1) AS score "
                    "FROM q, chunks c JOIN documents d USING (build_id, doc_id) "
                    "WHERE c.build_id = :b AND c.tsv @@ q.q"
                    + _KIND_FILTER
                    + " ORDER BY score DESC, c.chunk_id LIMIT :n"
                ),
                {"q": query, "b": build_id.value, "kinds": [k.value for k in kinds], "n": limit},
            ).all()
        return [_hit(r) for r in rows]

    def browse(
        self,
        build_id: BuildId,
        kinds: Sequence[DocumentKind] = (),
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        tag: str | None = None,
    ) -> tuple[list[DocumentSummary], int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.doc_id, d.kind, d.title, d.resource, d.method, d.path, "  # noqa: S608
                    "d.deprecated, d.tags, d.real_path, "
                    f"count(*) OVER () AS total FROM documents d WHERE {_BROWSE_FILTER} "
                    "ORDER BY d.kind, d.doc_id LIMIT :n OFFSET :o"
                ),
                {
                    "b": build_id.value,
                    "kinds": [k.value for k in kinds],
                    "q": query or None,
                    "like": f"%{_like(query)}%" if query else "%",
                    "tag": tag,
                    "n": limit,
                    "o": offset,
                },
            ).all()
            total = rows[0].total if rows else 0
            if not rows and offset > 0:
                total = conn.execute(
                    text(
                        f"SELECT count(*) FROM documents d WHERE {_BROWSE_FILTER}"  # noqa: S608
                    ),
                    {
                        "b": build_id.value,
                        "kinds": [k.value for k in kinds],
                        "q": query or None,
                        "like": f"%{_like(query)}%" if query else "%",
                        "tag": tag,
                    },
                ).scalar_one()
        return [_summary(r) for r in rows], int(total)

    def summaries(self, build_id: BuildId, doc_ids: Sequence[str]) -> dict[str, DocumentSummary]:
        if not doc_ids:
            return {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT doc_id, kind, title, resource, method, path, deprecated, tags, "
                    "real_path "
                    "FROM documents WHERE build_id = :b AND doc_id = ANY(:ids)"
                ),
                {"b": build_id.value, "ids": list(doc_ids)},
            ).all()
        return {r.doc_id: _summary(r) for r in rows}

    def counts(self, build_id: BuildId) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT kind, count(*) AS n FROM documents WHERE build_id = :b GROUP BY kind"),
                {"b": build_id.value},
            ).all()
            chunks = conn.execute(
                text("SELECT count(*) FROM chunks WHERE build_id = :b"), {"b": build_id.value}
            ).scalar_one()
            models = conn.execute(
                text(
                    "SELECT count(DISTINCT coalesce(shape, doc_id)) AS shapes, "
                    "count(DISTINCT lower(split_part(title, ' / ', -1))) FILTER ("
                    "WHERE resource IS NOT NULL) AS names "
                    "FROM documents WHERE build_id = :b AND kind = 'model'"
                ),
                {"b": build_id.value},
            ).one()
        out = {r.kind: int(r.n) for r in rows}
        out["chunks"] = int(chunks)
        out["model_shapes"] = int(models.shapes)
        out["model_names"] = int(models.names or 0)
        return out


_FACT_COLUMNS = (
    "kind, owner_id, owner_kind, resource, name, location, type, required, complete, "
    "doc_id, source_url, anchor, quote, constraints"
)


class PostgresFactQuery:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

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
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_FACT_COLUMNS} FROM facts WHERE build_id = :b "  # noqa: S608
                    "AND (lower(name) = lower(:n) OR lower(name) LIKE :suffix ESCAPE '\\') "
                    "AND (CAST(:kind AS text) IS NULL OR kind = :kind) "
                    "AND (CAST(:owner AS text) IS NULL OR owner_id = :owner) "
                    "AND (CAST(:res AS text) IS NULL OR lower(resource) = lower(:res)) "
                    "AND (CAST(:loc AS text) IS NULL OR location = :loc) "
                    "ORDER BY kind, owner_id, name, location"
                ),
                {
                    "b": build_id.value,
                    "n": name,
                    "suffix": f"%.{_like(name)}",
                    "kind": kind.value if kind else None,
                    "owner": owner_id,
                    "res": resource,
                    "loc": location.value if location else None,
                },
            ).all()
        return [fact_from_row(r) for r in rows]

    def field_names(self, build_id: BuildId) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT name FROM facts WHERE build_id = :b AND kind = 'field'"),
                {"b": build_id.value},
            ).all()
        return [r.name for r in rows]

    def for_owner(self, build_id: BuildId, owner_id: str) -> list[Fact]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_FACT_COLUMNS} FROM facts WHERE build_id = :b AND owner_id = :o "  # noqa: S608
                    "ORDER BY kind, name, location"
                ),
                {"b": build_id.value, "o": owner_id},
            ).all()
        return [fact_from_row(r) for r in rows]

    def endpoints(self, build_id: BuildId) -> list[Fact]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_FACT_COLUMNS} FROM facts WHERE build_id = :b AND kind = 'endpoint' "  # noqa: S608
                    "ORDER BY name"
                ),
                {"b": build_id.value},
            ).all()
        return [fact_from_row(r) for r in rows]

    def bounded_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> dict[str, int]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT doc_id, raw->>:key FROM documents WHERE build_id = :b "
                    "AND kind IN ('endpoint', 'model') AND raw->>:key IS NOT NULL "
                    "AND (CAST(:owner AS text) IS NULL OR doc_id = :owner) "
                    "AND (CAST(:res AS text) IS NULL OR lower(resource) = lower(:res)) "
                    "ORDER BY doc_id"
                ),
                {
                    "b": build_id.value,
                    "owner": owner_id,
                    "res": resource,
                    "key": FIELDS_BOUNDED_KEY,
                },
            ).all()
        return {str(doc): int(level) for doc, level in rows if str(level).isdigit()}

    def incomplete_owners(
        self, build_id: BuildId, *, owner_id: str | None = None, resource: str | None = None
    ) -> list[str]:
        with self._engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT doc_id FROM documents WHERE build_id = :b AND NOT complete "
                        "AND kind IN ('endpoint', 'model') "
                        "AND (CAST(:owner AS text) IS NULL OR doc_id = :owner) "
                        "AND (CAST(:res AS text) IS NULL OR lower(resource) = lower(:res)) "
                        "ORDER BY doc_id"
                    ),
                    {"b": build_id.value, "owner": owner_id, "res": resource},
                ).scalars()
            )
