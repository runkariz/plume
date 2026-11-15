from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Engine, text

from plume.application.ports.collection_repo import Collection


class PostgresCollectionRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self, collection_id: str, created_at: datetime, legacy_key_hash: str | None = None
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO collections (collection_id, created_at, legacy_key_hash) "
                    "VALUES (:c, :t, :h)"
                ),
                {"c": collection_id, "t": created_at, "h": legacy_key_hash},
            )

    def get(self, collection_id: str) -> Collection | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text(
                    "SELECT collection_id, created_at, merged_into FROM collections "
                    "WHERE collection_id = :c"
                ),
                {"c": collection_id},
            ).first()
        return Collection(r.collection_id, r.created_at, r.merged_into) if r else None

    def add(
        self,
        collection_id: str,
        kind: str,
        lineage_id: str,
        at: datetime,
        version_id: str | None = None,
    ) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO collection_items (collection_id, kind, lineage_id, added_at, "
                    "version_id) VALUES (:c, :k, :l, :t, :v) ON CONFLICT DO NOTHING"
                ),
                {"c": collection_id, "k": kind, "l": lineage_id, "t": at, "v": version_id},
            )
            created = bool(result.rowcount)
            if not created and version_id:
                conn.execute(
                    text(
                        "UPDATE collection_items SET version_id = :v WHERE collection_id = :c "
                        "AND kind = :k AND lineage_id = :l"
                    ),
                    {"c": collection_id, "k": kind, "l": lineage_id, "v": version_id},
                )
        return created

    def items(self, collection_id: str) -> list[tuple[str, str, str | None]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT kind, lineage_id, version_id FROM collection_items "
                    "WHERE collection_id = :c ORDER BY added_at DESC, lineage_id"
                ),
                {"c": collection_id},
            ).all()
        return [(r.kind, r.lineage_id, r.version_id) for r in rows]

    def containing(self, kind: str, lineage_id: str) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT collection_id FROM collection_items WHERE kind = :k "
                    "AND lineage_id = :l ORDER BY added_at, collection_id"
                ),
                {"k": kind, "l": lineage_id},
            ).all()
        return [r.collection_id for r in rows]

    def for_legacy_keys(self, key_hashes: Sequence[str]) -> list[str]:
        if not key_hashes:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT collection_id FROM collections WHERE legacy_key_hash = ANY(:h) "
                    "ORDER BY created_at, collection_id"
                ),
                {"h": list(key_hashes)},
            ).all()
        return [r.collection_id for r in rows]

    def merge(self, into: str, source: str, at: datetime) -> int:
        with self._engine.begin() as conn:
            moved = conn.execute(
                text(
                    "INSERT INTO collection_items (collection_id, kind, lineage_id, added_at, "
                    "version_id) SELECT :i, kind, lineage_id, :t, version_id "
                    "FROM collection_items WHERE collection_id = :s ON CONFLICT "
                    "(collection_id, kind, lineage_id) DO UPDATE SET version_id = "
                    "COALESCE(collection_items.version_id, EXCLUDED.version_id) "
                    "WHERE collection_items.version_id IS NULL AND EXCLUDED.version_id IS NOT NULL"
                ),
                {"i": into, "s": source, "t": at},
            ).rowcount
            conn.execute(
                text("DELETE FROM collection_items WHERE collection_id = :s"), {"s": source}
            )
            conn.execute(
                text("UPDATE collections SET merged_into = :i WHERE collection_id = :s"),
                {"i": into, "s": source},
            )
        return int(moved or 0)
