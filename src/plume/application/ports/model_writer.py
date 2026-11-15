"""Port: an LLM that writes a canonical-model draft (server-side generation, maintainer only)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from plume.application.errors import ApplicationError


class ModelWriterUnavailableError(ApplicationError):
    """No LLM is configured (e.g. no Vertex key file)."""

    code = "llm_unavailable"


class ModelWriterError(ApplicationError):
    code = "llm_failed"


@dataclass(frozen=True, slots=True)
class Turn:
    role: Literal["user", "model"]
    text: str


class ModelWriter(Protocol):
    @property
    def name(self) -> str:
        """Recorded as the snapshot's generator, e.g. ``gemini:gemini-4-argon``."""
        ...

    def available(self) -> bool: ...

    @property
    def last_usage(self) -> dict[str, int] | None:
        """Token counts of the last call ({prompt, response, total, thoughts?}), if reported."""
        ...

    def write(self, system: str, turns: Sequence[Turn]) -> str:
        """The model's reply (expected: one JSON object). Raises ``ModelWriterUnavailableError``
        or ``ModelWriterError``."""
        ...
