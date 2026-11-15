from typing import Any

from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build, BuildSpec, BuildStatus
from plume.domain.shared.hashing import ContentHash
from plume.domain.shared.ids import BuildId

_SELECT = """
SELECT build_id, api_id, status, created_at, sealed_at, content_hash, package_hash,
       chunker_version, embed_model, dims, source_ref, run_id
FROM builds
"""


class PostgresBuildRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _load(conn: Connection, row: Any) -> Build:
        items = conn.execute(
            text("SELECT item_id, content_hash FROM build_items WHERE build_id = :b"),
            {"b": row.build_id},
        ).all()
        spec = None
        if row.package_hash is not None:
            spec = BuildSpec(
                package_hash=row.package_hash,
                chunker_version=row.chunker_version,
                embed_model=row.embed_model,
                dims=row.dims,
                source_ref=row.source_ref,
                run_id=row.run_id,
            )
        return Build(
            api_id=ApiId(row.api_id),
            build_id=BuildId(row.build_id),
            created_at=row.created_at,
            status=BuildStatus(row.status),
            _items={i.item_id: ContentHash(i.content_hash) for i in items},
            content_hash=ContentHash(row.content_hash) if row.content_hash else None,
            sealed_at=row.sealed_at,
            spec=spec,
        )

    def get(self, build_id: BuildId) -> Build | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(_SELECT + " WHERE build_id = :b"), {"b": build_id.value}
            ).one_or_none()
            return self._load(conn, row) if row else None

    def list(self, api_id: ApiId) -> list[Build]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(_SELECT + " WHERE api_id = :a ORDER BY created_at DESC, build_id"),
                {"a": api_id.value},
            ).all()
            return [self._load(conn, r) for r in rows]

    def save(self, build: Build) -> None:
        spec = build.spec
        with self._engine.begin() as conn:
            current = conn.execute(
                text("SELECT status FROM builds WHERE build_id = :b FOR UPDATE"),
                {"b": build.build_id.value},
            ).scalar_one_or_none()
            if current == BuildStatus.SEALED.value:
                if build.is_sealed:
                    return  # sealed builds never change; saving the same build is a no-op
                raise ValueError(f"build {build.build_id} is sealed in storage")
            conn.execute(
                text(
                    """
                    INSERT INTO builds (build_id, api_id, status, created_at, sealed_at,
                        content_hash, package_hash, chunker_version, embed_model, dims,
                        source_ref, run_id)
                    VALUES (:b, :a, :s, :c, :sa, :h, :ph, :cv, :em, :d, :sr, :r)
                    ON CONFLICT (build_id) DO UPDATE SET
                        status = EXCLUDED.status, sealed_at = EXCLUDED.sealed_at,
                        content_hash = EXCLUDED.content_hash
                    """
                ),
                {
                    "b": build.build_id.value,
                    "a": build.api_id.value,
                    "s": build.status.value,
                    "c": build.created_at,
                    "sa": build.sealed_at,
                    "h": build.content_hash.value if build.content_hash else None,
                    "ph": spec.package_hash if spec else None,
                    "cv": spec.chunker_version if spec else None,
                    "em": spec.embed_model if spec else None,
                    "d": spec.dims if spec else None,
                    "sr": spec.source_ref if spec else None,
                    "r": spec.run_id if spec else None,
                },
            )
            conn.execute(
                text("DELETE FROM build_items WHERE build_id = :b"), {"b": build.build_id.value}
            )
            if build.items:
                conn.execute(
                    text(
                        "INSERT INTO build_items (build_id, item_id, content_hash) "
                        "VALUES (:b, :i, :h)"
                    ),
                    [
                        {"b": build.build_id.value, "i": k, "h": v.value}
                        for k, v in build.items.items()
                    ],
                )
