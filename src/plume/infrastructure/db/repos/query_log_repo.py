import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from plume.domain.querylog.event import QueryEvent

_COLUMNS = (
    "occurred_at", "schema_version", "surface", "tool", "api", "apis", "build_id",
    "version_requested", "query_text", "call_method", "call_path_template", "param_names",
    "fact_kind", "fact_name", "doc_id", "top_docs", "result_count", "verdict", "complete",
    "answered_by", "error_class", "latency_ms", "client_name", "session_hash", "redactions",
)  # fmt: skip


def _row(e: QueryEvent) -> dict[str, Any]:
    d = e.as_dict()
    d["occurred_at"] = e.occurred_at
    d["top_docs"] = json.dumps(d["top_docs"])
    return {k: d[k] for k in _COLUMNS}


class PostgresQueryLogRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_many(self, events: Sequence[QueryEvent]) -> None:
        if not events:
            return
        cols = ", ".join(_COLUMNS)
        values = ", ".join(f"CAST(:{c} AS jsonb)" if c == "top_docs" else f":{c}" for c in _COLUMNS)
        with self._engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO query_events ({cols}) VALUES ({values})"),  # noqa: S608
                [_row(e) for e in events],
            )

    def purge(self, before: datetime) -> int:
        with self._engine.begin() as conn:
            r = conn.execute(text("DELETE FROM query_events WHERE occurred_at < :t"), {"t": before})
            return int(r.rowcount or 0)

    def export(self, since: datetime | None, api: str | None) -> Iterator[QueryEvent]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM query_events WHERE TRUE"  # noqa: S608
        params: dict[str, Any] = {}
        if since is not None:
            sql += " AND occurred_at >= :since"
            params["since"] = since
        if api is not None:
            sql += " AND api = :api"
            params["api"] = api
        sql += " ORDER BY occurred_at, id"
        with self._engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(text(sql), params)
            for r in result.mappings():
                yield QueryEvent(
                    occurred_at=r["occurred_at"], surface=r["surface"], tool=r["tool"],
                    api=r["api"], apis=tuple(r["apis"] or ()), build_id=r["build_id"],
                    version_requested=r["version_requested"], query_text=r["query_text"],
                    call_method=r["call_method"], call_path_template=r["call_path_template"],
                    param_names=tuple(r["param_names"] or ()), fact_kind=r["fact_kind"],
                    fact_name=r["fact_name"], doc_id=r["doc_id"],
                    top_docs=tuple((t["doc_id"], t["rank"]) for t in r["top_docs"] or []),
                    result_count=r["result_count"], verdict=r["verdict"],
                    complete=r["complete"], answered_by=r["answered_by"],
                    error_class=r["error_class"], latency_ms=r["latency_ms"],
                    client_name=r["client_name"], session_hash=r["session_hash"],
                    redactions=r["redactions"], schema_version=r["schema_version"],
                )  # fmt: skip
