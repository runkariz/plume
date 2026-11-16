from collections.abc import Mapping
from typing import Any, Protocol

from plume.domain.knowledge.api import ApiId


class ApiRemoval(Protocol):
    def remove(self, api_id: ApiId, audit: Mapping[str, Any]) -> dict[str, int]:
        """Delete the API with all its builds (documents, chunks, facts, assets, evals), tags,
        release notes, package meta, jobs and display name, and write the audit row, in ONE
        transaction. Returns the row counts removed per kind."""
        ...
