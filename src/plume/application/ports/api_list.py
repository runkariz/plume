"""A read model for the API list (GET /v1/apis): everything the list shows for all APIs in a
few queries, instead of eight round trips per API."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from plume.application.ports.eval_repo import EvalRecord
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import BuildSpec


@dataclass(frozen=True, slots=True)
class LatestBuild:
    """What the list shows of the build an API's ``latest`` tag points at (never its items:
    47k hashes for 45 APIs)."""

    build_id: str
    created_at: datetime
    sealed_at: datetime | None
    spec: BuildSpec | None

    @property
    def docs_as_of(self) -> str:  # as ResolvedBuild.docs_as_of
        return (self.sealed_at or self.created_at).date().isoformat()


@dataclass(frozen=True, slots=True)
class ApiListRow:
    """One API's list data: its tags (by name), its latest build, and that build's counts,
    eval and icon."""

    tags: tuple[str, ...]
    latest: LatestBuild | None
    counts: Mapping[str, int] = field(default_factory=dict)
    eval: EvalRecord | None = None
    has_icon: bool = False


class ApiListQuery(Protocol):
    def rows(self, api_ids: Sequence[ApiId]) -> dict[ApiId, ApiListRow]: ...
