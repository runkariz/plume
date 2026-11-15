import json
from typing import Any

from sqlalchemy import Connection, Engine, text

from plume.application.ports.eval_repo import EvalRecord
from plume.domain.eval.metrics import EvalMetrics
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.ids import BuildId


def save_eval(conn: Connection, r: EvalRecord) -> None:
    conn.execute(
        text(
            """
            INSERT INTO evals (build_id, api_id, gold_hash, metrics, passed, message,
                               baseline_build, details, evaluated_at)
            VALUES (:b, :a, :g, CAST(:m AS jsonb), :p, :msg, :base, CAST(:d AS jsonb), :t)
            ON CONFLICT (build_id) DO UPDATE SET
                gold_hash = EXCLUDED.gold_hash, metrics = EXCLUDED.metrics,
                passed = EXCLUDED.passed, message = EXCLUDED.message,
                baseline_build = EXCLUDED.baseline_build, details = EXCLUDED.details,
                evaluated_at = EXCLUDED.evaluated_at
            """
        ),
        {
            "b": r.build_id.value,
            "a": r.api_id.value,
            "g": r.gold_hash,
            "m": json.dumps(r.metrics.as_dict()),
            "p": r.passed,
            "msg": r.message,
            "base": r.baseline_build.value if r.baseline_build else None,
            "d": json.dumps(list(r.details)),
            "t": r.evaluated_at,
        },
    )


def eval_from_row(row: Any) -> EvalRecord:
    metrics = row.metrics if isinstance(row.metrics, dict) else json.loads(row.metrics)
    details = row.details if isinstance(row.details, list) else json.loads(row.details)
    return EvalRecord(
        build_id=BuildId(row.build_id),
        api_id=ApiId(row.api_id),
        gold_hash=row.gold_hash,
        metrics=EvalMetrics.from_dict(metrics),
        passed=row.passed,
        message=row.message,
        baseline_build=BuildId(row.baseline_build) if row.baseline_build else None,
        evaluated_at=row.evaluated_at,
        details=tuple(details),
    )


class PostgresEvalRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, record: EvalRecord) -> None:
        with self._engine.begin() as conn:
            save_eval(conn, record)

    def get(self, build_id: BuildId) -> EvalRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM evals WHERE build_id = :b"), {"b": build_id.value}
            ).one_or_none()
        return eval_from_row(row) if row else None
