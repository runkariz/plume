"""``BuildImporter``: restore a snapshot in ONE transaction (all or nothing)."""

import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Engine, text

from plume.application.ports.dump_store import BuildSnapshot
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId
from plume.infrastructure.db.repos._codec import vector_literal
from plume.infrastructure.db.repos.api_repo import upsert_api
from plume.infrastructure.db.repos.asset_repo import put_assets
from plume.infrastructure.db.repos.build_repo import save_build
from plume.infrastructure.db.repos.document_repo import insert_documents, replace_chunks
from plume.infrastructure.db.repos.eval_repo import save_eval
from plume.infrastructure.db.repos.tag_repo import set_tag
from plume.infrastructure.search.postgres_fact_index import replace_facts


class PostgresBuildImporter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, build_id: BuildId) -> bool:
        with self._engine.connect() as conn:
            return (
                conn.execute(
                    text("SELECT 1 FROM builds WHERE build_id = :b"), {"b": build_id.value}
                ).scalar()
                is not None
            )

    def restore(self, snapshot: BuildSnapshot, tags: Sequence[str] = ()) -> None:
        b = snapshot.build
        with self._engine.begin() as conn:
            if conn.execute(
                text("SELECT 1 FROM builds WHERE build_id = :b FOR UPDATE"), {"b": b.build_id.value}
            ).scalar():
                raise ValueError(f"build {b.build_id} already exists")
            upsert_api(conn, snapshot.api)
            save_build(conn, b)
            insert_documents(conn, b.build_id, snapshot.documents)
            replace_chunks(conn, b.build_id, snapshot.chunks)
            if snapshot.vectors:
                conn.execute(
                    text(
                        "UPDATE chunks SET embedding = CAST(:v AS halfvec) "
                        "WHERE build_id = :b AND chunk_id = :c"
                    ),
                    [
                        {"b": b.build_id.value, "c": cid, "v": vector_literal(v)}
                        for cid, v in snapshot.vectors.items()
                    ],
                )
                if b.spec is not None:
                    chunks = {c.chunk_id: c for c in snapshot.chunks}
                    conn.execute(
                        text(
                            "INSERT INTO embed_cache (embed_hash, model, dims, embedding) "
                            "VALUES (:h, :m, :d, CAST(:v AS halfvec)) "
                            "ON CONFLICT (embed_hash, model, dims) DO NOTHING"
                        ),
                        [
                            {
                                "h": chunks[cid].embed_hash.value,
                                "m": b.spec.embed_model,
                                "d": b.spec.dims,
                                "v": vector_literal(v),
                            }
                            for cid, v in snapshot.vectors.items()
                        ],
                    )
            replace_facts(conn, b.build_id, snapshot.facts)
            if snapshot.eval is not None:
                save_eval(conn, snapshot.eval)
            if snapshot.assets:
                put_assets(conn, b.build_id, snapshot.assets)
            if snapshot.package_meta:
                conn.execute(
                    text(
                        "INSERT INTO build_package_meta (build_id, meta) "
                        "VALUES (:b, CAST(:m AS jsonb)) ON CONFLICT (build_id) DO NOTHING"
                    ),
                    {"b": b.build_id.value, "m": json.dumps(dict(snapshot.package_meta))},
                )
            if snapshot.release_notes:
                n = snapshot.release_notes
                conn.execute(
                    text(
                        "INSERT INTO release_notes (to_build, api_id, from_build, computed_at, "
                        "review, body) VALUES (:t, :a, :f, :c, :r, CAST(:j AS jsonb)) "
                        "ON CONFLICT (to_build) DO NOTHING"
                    ),
                    {
                        "t": n["to"],
                        "a": n["api"],
                        "f": n["from"],
                        "c": datetime.fromisoformat(n["computedAt"]),
                        "r": n["review"],
                        "j": json.dumps(dict(n), ensure_ascii=False),
                    },
                )
            for name in tags:
                set_tag(conn, Tag.point(TagName(name), b))
