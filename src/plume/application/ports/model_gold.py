"""Where model gold files come from (see ``domain.models.model_gold``)."""

from typing import Protocol

from plume.domain.models.model_gold import GoldModel


class ModelGoldSource(Protocol):
    def load(self, ref: str) -> tuple[GoldModel, ...]:
        """One gold file: a path (CLI), or a file name inside the configured gold dirs."""
        ...

    def all(self) -> tuple[GoldModel, ...]:
        """Every gold model of the configured dirs (empty when none is configured)."""
        ...
