from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.api_list import ApiListRow, LatestBuild
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.asset import ICON
from plume.domain.knowledge.build import BuildSpec
from plume.domain.knowledge.tag import LATEST
from plume.infrastructure.db.repos.build_repo import _SELECT
from plume.infrastructure.db.repos.eval_repo import eval_from_row


class PostgresApiListQuery:
    """The API list's data in six queries for all APIs (tags, latest builds, three counts,
    evals and icons), the same values ListApiOverviews reads one API at a time."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def rows(self, api_ids: Sequence[ApiId]) -> dict[ApiId, ApiListRow]:
        ids = [a.value for a in api_ids]
        with self._engine.connect() as conn:
            tags = conn.execute(
                text("SELECT api_id, name, build_id FROM tags WHERE api_id = ANY(:a) "
                     "ORDER BY api_id, name"),
                {"a": ids},
            ).all()  # fmt: skip
            names: dict[str, list[str]] = defaultdict(list)
            latest_of: dict[str, str] = {}
            for t in tags:
                names[t.api_id].append(t.name)
                if t.name == LATEST:
                    latest_of[t.api_id] = t.build_id
            bids = list(latest_of.values())
            builds = {
                r.build_id: _latest(r)
                for r in conn.execute(text(_SELECT + " WHERE build_id = ANY(:b)"), {"b": bids})
            }
            counts: dict[str, dict[str, int]] = defaultdict(dict)
            for r in conn.execute(
                text("SELECT build_id, kind, count(*) AS n FROM documents "
                     "WHERE build_id = ANY(:b) GROUP BY build_id, kind"),
                {"b": bids},
            ):  # fmt: skip
                counts[r.build_id][r.kind] = int(r.n)
            chunks = dict.fromkeys(bids, 0) | {
                r.build_id: int(r.n)
                for r in conn.execute(
                    text("SELECT build_id, count(*) AS n FROM chunks WHERE build_id = ANY(:b) "
                         "GROUP BY build_id"),
                    {"b": bids},
                )
            }  # fmt: skip
            models: dict[str, Any] = {
                r.build_id: r
                for r in conn.execute(
                    text(
                        "SELECT build_id, count(DISTINCT coalesce(shape, doc_id)) AS shapes, "
                        "count(DISTINCT lower(split_part(title, ' / ', -1))) FILTER ("
                        "WHERE resource IS NOT NULL) AS names "
                        "FROM documents WHERE build_id = ANY(:b) AND kind = 'model' "
                        "GROUP BY build_id"
                    ),
                    {"b": bids},
                )
            }
            evals = {
                r.build_id: eval_from_row(r)
                for r in conn.execute(
                    text("SELECT * FROM evals WHERE build_id = ANY(:b)"), {"b": bids}
                )
            }
            icons = {
                r.build_id
                for r in conn.execute(
                    text("SELECT build_id FROM build_assets WHERE name = :n "
                         "AND build_id = ANY(:b)"),
                    {"n": ICON, "b": bids},
                )
            }  # fmt: skip
        out: dict[ApiId, ApiListRow] = {}
        for api_id in api_ids:
            bid = latest_of.get(api_id.value)
            if bid is None or bid not in builds:  # no latest tag: no published build
                out[api_id] = ApiListRow(tuple(names.get(api_id.value, ())), None)
                continue
            build = builds[bid]
            c = dict(counts.get(bid, {}))
            c["chunks"] = chunks.get(bid, 0)
            m = models.get(bid)
            c["model_shapes"] = int(m.shapes) if m else 0
            c["model_names"] = int(m.names or 0) if m else 0
            out[api_id] = ApiListRow(
                tuple(names[api_id.value]),
                build,
                c,
                evals.get(bid),
                bid in icons,
            )
        return out


def _latest(row: Any) -> LatestBuild:
    spec = None
    if row.package_hash is not None:  # as PostgresBuildRepo._load
        spec = BuildSpec(
            package_hash=row.package_hash,
            chunker_version=row.chunker_version,
            embed_model=row.embed_model,
            dims=row.dims,
            source_ref=row.source_ref,
            run_id=row.run_id,
        )
    return LatestBuild(row.build_id, row.created_at, row.sealed_at, spec)
