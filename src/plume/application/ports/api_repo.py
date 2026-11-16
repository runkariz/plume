from typing import Protocol

from plume.domain.knowledge.api import ApiId, ApiInfo


class ApiRepo(Protocol):
    def upsert(self, info: ApiInfo) -> None: ...

    def get(self, api_id: ApiId) -> ApiInfo | None: ...

    def list(self) -> list[ApiInfo]: ...

    def set_display_name(self, api_id: ApiId, name: str | None) -> None:
        """The maintainer's display name for the API (None clears it); kept across loads."""
