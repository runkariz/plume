"""The maintainer's display name for an API. Packages may carry only an id-like app.json `name`
("amazon-sp-vendor"); the override is stored per API (not per build), survives reloads and wins
over the package title and the derived name."""

from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.api_repo import ApiRepo
from plume.domain.knowledge.api import ApiId

MAX_NAME = 80


class DisplayNameError(ApplicationError):
    code = "invalid_input"


class ApiDisplayName:
    def __init__(self, apis: ApiRepo) -> None:
        self._apis = apis

    def set(self, api: str, name: str | None) -> dict[str, Any]:
        """Set (or, with None, clear) the display name; returns the resolved name."""
        api_id = ApiId(api)
        if self._apis.get(api_id) is None:
            raise NotFoundError(f"unknown api {api}")
        if name is not None:
            name = " ".join(name.split())
            if not name or len(name) > MAX_NAME:
                raise DisplayNameError(f"name must be 1-{MAX_NAME} characters (null clears it)")
        self._apis.set_display_name(api_id, name)
        info = self._apis.get(api_id)
        if info is None:
            raise NotFoundError(f"unknown api {api}")
        return {
            "api": api,
            "name": info.display_name,
            "nameSource": info.display_source,
            "packageName": info.name,
        }
