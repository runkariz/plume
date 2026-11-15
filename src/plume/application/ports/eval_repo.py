"""Ports: gold sets and stored eval results."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from plume.domain.eval.gold import GoldSet
from plume.domain.eval.metrics import EvalMetrics
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.ids import BuildId


@dataclass(frozen=True, slots=True)
class EvalRecord:
    build_id: BuildId
    api_id: ApiId
    gold_hash: str
    metrics: EvalMetrics
    passed: bool
    message: str
    baseline_build: BuildId | None
    evaluated_at: datetime
    details: tuple[dict[str, object], ...] = ()


class GoldSource(Protocol):
    def load(self, ref: str) -> tuple[GoldSet, str]:
        """The gold set at ``ref`` and its content hash."""
        ...

    def for_api(self, api: str) -> str | None:
        """The default gold set reference for an API, if one is configured."""
        ...


class EvalRepo(Protocol):
    def save(self, record: EvalRecord) -> None:
        """Store (or replace) the eval of a build."""
        ...

    def get(self, build_id: BuildId) -> EvalRecord | None: ...
