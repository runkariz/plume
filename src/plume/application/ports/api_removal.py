from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from plume.domain.knowledge.api import ApiId


class ApiRemoval(Protocol):
    def remove(
        self, api_id: ApiId, audit: Mapping[str, Any], retire: Sequence[Mapping[str, str]] = ()
    ) -> dict[str, int]:
        """In ONE transaction: retire the models/sets in `retire` ({type "model"|"set", id,
        now: the new visibility}), delete the API with all its builds (documents, chunks,
        facts, assets, evals), tags, release notes, package meta, jobs and display name, and
        write the audit row. Returns the row counts removed per kind."""
        ...
