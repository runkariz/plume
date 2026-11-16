"""Removing an API (maintainer): the API, all its builds, tags, evals, release notes, package
meta, jobs and display name, in one transaction with an audit row. Refused while official or
unreleased models or sets pin its builds, unless forced: then those are taken out of the
catalogue explicitly first (official -> superseded, unreleased -> discarded)."""

from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.api_removal import ApiRemoval
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.model_repo import ModelRepo
from plume.application.ports.model_set_repo import ModelSetRepo
from plume.domain.knowledge.api import ApiId
from plume.domain.models.snapshot import Visibility

LISTED = (Visibility.OFFICIAL, Visibility.UNRELEASED)
_RETIRED = {Visibility.OFFICIAL: Visibility.SUPERSEDED, Visibility.UNRELEASED: Visibility.DISCARDED}
SCAN_LIMIT = 10_000


class RemoveInputError(ApplicationError):
    code = "invalid_input"


class ApiInUseError(ApplicationError):
    code = "api_in_use"

    def __init__(self, api: str, pinned: list[dict[str, Any]]) -> None:
        super().__init__(
            f"{len(pinned)} official/unreleased model(s) or set(s) pin {api}'s builds; "
            "remove with force=true to retire them (official -> superseded, unreleased -> "
            "discarded)"
        )
        self.pinned = pinned


class RemoveApi:
    def __init__(
        self, apis: ApiRepo, removal: ApiRemoval, models: ModelRepo, sets: ModelSetRepo
    ) -> None:
        self._apis = apis
        self._removal = removal
        self._models = models
        self._sets = sets

    def pinned_by(self, api: str) -> list[dict[str, Any]]:
        """Official and unreleased models and sets that pin this API's builds."""
        out: list[dict[str, Any]] = [
            {
                "type": "model",
                "id": m.snapshot_id,
                "name": m.draft.name,
                "visibility": m.visibility,
            }
            for m in self._models.list_snapshots(api, SCAN_LIMIT, LISTED)
        ]
        for x in self._sets.list_sets(api, SCAN_LIMIT, LISTED):
            out.append(
                {"type": "set", "id": x.set_id, "name": x.draft.name, "visibility": x.visibility}
            )
        return out

    def execute(
        self, api: str, confirm: str, force: bool = False, reason: str | None = None
    ) -> dict[str, Any]:
        api_id = ApiId(api)
        if confirm != api:
            raise RemoveInputError(f"type the API id to confirm: confirm must be {api!r}")
        if self._apis.get(api_id) is None:
            raise NotFoundError(f"unknown api {api}")
        pinned = self.pinned_by(api)
        if pinned and not force:
            raise ApiInUseError(api, pinned)
        retired = []
        for p in pinned:  # explicit, before the data goes
            new = _RETIRED[p["visibility"]]
            if p["type"] == "model":
                self._models.set_visibility(p["id"], new, None)
            else:
                self._sets.set_visibility(p["id"], new, None)
            retired.append({**p, "now": new})
        counts = self._removal.remove(
            api_id, {"forced": force, "reason": reason, "affected": retired}
        )
        return {"api": api, "removed": counts, "retired": retired, "forced": force}
