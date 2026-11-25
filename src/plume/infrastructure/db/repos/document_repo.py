import json
from collections.abc import Sequence

from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document, DocumentKind
from plume.domain.shared.ids import BuildId
from plume.infrastructure.db.repos._codec import document_from_row, fields_to_json

_DOC_COLUMNS = (
    "doc_id, kind, title, text, source_url, anchor, resource, method, path, deprecated, "
    "complete, fields, scopes, source_id, shape, tags, raw, real_path, rate_limit"
)


def replace_chunks(conn: Connection, build_id: BuildId, chunks: Sequence[Chunk]) -> None:
    keep = [c.chunk_id for c in chunks]
    conn.execute(
        text("DELETE FROM chunks WHERE build_id = :b AND NOT (chunk_id = ANY(:keep))"),
        {"b": build_id.value, "keep": keep},
    )
    if not chunks:
        return
    conn.execute(
        text(
            """
            INSERT INTO chunks (build_id, chunk_id, doc_id, ordinal, heading, text,
                                embed_hash, content_hash)
            VALUES (:b, :c, :d, :o, :h, :t, :eh, :ch)
            ON CONFLICT (build_id, chunk_id) DO UPDATE SET
                doc_id = EXCLUDED.doc_id, ordinal = EXCLUDED.ordinal,
                heading = EXCLUDED.heading, text = EXCLUDED.text,
                content_hash = EXCLUDED.content_hash,
                embedding = CASE WHEN chunks.embed_hash = EXCLUDED.embed_hash
                                 THEN chunks.embedding END,
                embed_hash = EXCLUDED.embed_hash
            """
        ),
        [
            {
                "b": build_id.value,
                "c": c.chunk_id,
                "d": c.doc_id,
                "o": c.ordinal,
                "h": c.heading,
                "t": c.text,
                "eh": c.embed_hash.value,
                "ch": c.content_hash.value,
            }
            for c in chunks
        ],
    )


def insert_documents(conn: Connection, build_id: BuildId, documents: Sequence[Document]) -> None:
    if not documents:
        return
    rows = [
        {
            "b": build_id.value,
            "doc_id": d.doc_id,
            "kind": d.kind.value,
            "title": d.title,
            "text": d.text,
            "source_url": d.source_url,
            "anchor": d.anchor,
            "resource": d.resource,
            "method": d.method,
            "path": d.path,
            "deprecated": d.deprecated,
            "complete": d.complete,
            "fields": fields_to_json(d.fields),
            "scopes": list(d.scopes),
            "source_id": d.source_id,
            "shape": d.shape,
            "tags": list(d.tags),
            "raw": json.dumps(d.raw) if d.raw is not None else None,
            "real_path": d.real_path,
            "rate_limit": d.rate_limit,
            "content_hash": d.content_hash.value,
        }
        for d in documents
    ]
    conn.execute(
        text(
            f"""
            INSERT INTO documents (build_id, {_DOC_COLUMNS}, content_hash)
            VALUES (:b, :doc_id, :kind, :title, :text, :source_url, :anchor, :resource,
                    :method, :path, :deprecated, :complete, CAST(:fields AS jsonb),
                    :scopes, :source_id, :shape, :tags, CAST(:raw AS jsonb), :real_path,
                    :rate_limit, :content_hash)
            ON CONFLICT (build_id, doc_id) DO UPDATE SET
                kind = EXCLUDED.kind, title = EXCLUDED.title, text = EXCLUDED.text,
                source_url = EXCLUDED.source_url, anchor = EXCLUDED.anchor,
                resource = EXCLUDED.resource, method = EXCLUDED.method,
                path = EXCLUDED.path, deprecated = EXCLUDED.deprecated,
                complete = EXCLUDED.complete, fields = EXCLUDED.fields,
                scopes = EXCLUDED.scopes, source_id = EXCLUDED.source_id,
                shape = EXCLUDED.shape, tags = EXCLUDED.tags, raw = EXCLUDED.raw,
                real_path = EXCLUDED.real_path, rate_limit = EXCLUDED.rate_limit,
                content_hash = EXCLUDED.content_hash
            """  # noqa: S608 - constant column list
        ),
        rows,
    )


class PostgresDocumentRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_documents(self, build_id: BuildId, documents: Sequence[Document]) -> None:
        with self._engine.begin() as conn:
            insert_documents(conn, build_id, documents)

    def list_documents(self, build_id: BuildId) -> list[Document]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_DOC_COLUMNS} FROM documents WHERE build_id = :b ORDER BY doc_id"  # noqa: S608
                ),
                {"b": build_id.value},
            ).all()
        return [document_from_row(r) for r in rows]

    def get_document(self, build_id: BuildId, doc_id: str) -> Document | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT {_DOC_COLUMNS} FROM documents WHERE build_id = :b AND doc_id = :d"  # noqa: S608
                ),
                {"b": build_id.value, "d": doc_id},
            ).one_or_none()
        return document_from_row(row) if row else None

    def by_source_ids(
        self, build_id: BuildId, kind: DocumentKind, source_ids: Sequence[str]
    ) -> dict[str, Document]:
        if not source_ids:
            return {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_DOC_COLUMNS} FROM documents WHERE build_id = :b AND kind = :k "  # noqa: S608
                    "AND source_id = ANY(:ids)"
                ),
                {"b": build_id.value, "k": kind.value, "ids": list(source_ids)},
            ).all()
        docs = [document_from_row(r) for r in rows]
        return {d.source_id: d for d in docs if d.source_id}

    def model_users(self, build_id: BuildId, model_id: str) -> list[tuple[str, tuple[str, ...]]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.doc_id, array_agg(DISTINCT f->>'location') FROM documents d, "
                    "jsonb_array_elements(d.fields) f WHERE d.build_id = :b "
                    "AND d.kind IN ('endpoint', 'trigger') AND d.fields @> CAST(:pat AS jsonb) "
                    "AND f->>'model_id' = :m GROUP BY d.doc_id ORDER BY d.doc_id"
                ),
                {"b": build_id.value, "m": model_id, "pat": json.dumps([{"model_id": model_id}])},
            ).all()
        return [(r[0], tuple(sorted(x for x in r[1] if x))) for r in rows]

    def replace_chunks(self, build_id: BuildId, chunks: Sequence[Chunk]) -> None:
        with self._engine.begin() as conn:
            replace_chunks(conn, build_id, chunks)

    def list_chunks(self, build_id: BuildId) -> list[Chunk]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT chunk_id, doc_id, ordinal, heading, text FROM chunks "
                    "WHERE build_id = :b ORDER BY chunk_id"
                ),
                {"b": build_id.value},
            ).all()
        return [
            Chunk(
                chunk_id=r.chunk_id,
                doc_id=r.doc_id,
                ordinal=r.ordinal,
                heading=r.heading,
                text=r.text,
            )
            for r in rows
        ]
