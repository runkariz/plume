from collections.abc import Sequence
from typing import Protocol

from plume.domain.knowledge.fact import Fact
from plume.domain.shared.ids import BuildId


class FactIndex(Protocol):
    def replace_facts(self, build_id: BuildId, facts: Sequence[Fact]) -> None: ...

    def list_facts(self, build_id: BuildId) -> list[Fact]:
        """All facts of a build, ordered by fact id."""
        ...
