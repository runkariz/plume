"""Where model gold files come from (see ``domain.models.model_gold``)."""

from typing import Protocol

from plume.domain.models.model_gold import GoldModel
from plume.domain.models.set_gold import SetGold


class ModelGoldSource(Protocol):
    def load(self, ref: str) -> tuple[GoldModel, ...]:
        """One gold file: a path (CLI), or a file name inside the configured gold dirs."""
        ...

    def all(self) -> tuple[GoldModel, ...]:
        """Every gold model of the configured dirs (empty when none is configured)."""
        ...

    def sets(self) -> tuple[SetGold, ...]:
        """Every set gold (plume.set-gold.v1) of the configured dirs."""
        ...

    def load_sets(self, ref: str) -> tuple[SetGold, ...]:
        """One file's set gold (empty when it is a model gold file)."""
        ...
