"""Removing an API: one transaction over every table that holds its data."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Engine, text

from plume.domain.knowledge.api import ApiId

_BUILDS = "SELECT build_id FROM builds WHERE api_id = :a"
# Order matters: rows that point at builds go before the builds (cascades cover documents,
# chunks, facts, build items, assets and evals).
_STEPS = (
    ("releaseNotes", "DELETE FROM release_notes WHERE api_id = :a"),
    ("packageMeta", f"DELETE FROM build_package_meta WHERE build_id IN ({_BUILDS})"),  # noqa: S608
    ("tags", "DELETE FROM tags WHERE api_id = :a"),
    ("jobs", "DELETE FROM jobs WHERE api_id = :a"),
    ("evals", "DELETE FROM evals WHERE api_id = :a"),
    ("builds", "DELETE FROM builds WHERE api_id = :a"),
    ("displayName", "DELETE FROM api_display_names WHERE api_id = :a"),
    ("api", "DELETE FROM apis WHERE api_id = :a"),
)


_RETIRE = {"model": ("model_snapshots", "snapshot_id"), "set": ("model_sets", "set_id")}


class PostgresApiRemoval:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def remove(
        self, api_id: ApiId, audit: Mapping[str, Any], retire: Sequence[Mapping[str, str]] = ()
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._engine.begin() as conn:
            for r in retire:  # first, in the same transaction: all or nothing
                table, key = _RETIRE[r["type"]]
                conn.execute(
                    text(
                        f"UPDATE {table} SET visibility = :v, released_at = NULL "  # noqa: S608
                        f"WHERE {key} = :id"
                    ),
                    {"v": r["now"], "id": r["id"]},
                )
            counts["documents"] = int(
                conn.execute(
                    text(f"SELECT count(*) FROM documents WHERE build_id IN ({_BUILDS})"),  # noqa: S608
                    {"a": api_id.value},
                ).scalar_one()
            )
            for name, sql in _STEPS:
                counts[name] = conn.execute(text(sql), {"a": api_id.value}).rowcount or 0
            conn.execute(
                text(
                    "INSERT INTO api_removals (api_id, forced, reason, counts, affected) "
                    "VALUES (:a, :f, :r, CAST(:c AS jsonb), CAST(:x AS jsonb))"
                ),
                {
                    "a": api_id.value,
                    "f": bool(audit.get("forced")),
                    "r": audit.get("reason"),
                    "c": json.dumps(counts),
                    "x": json.dumps(audit.get("affected") or []),
                },
            )
        return counts
