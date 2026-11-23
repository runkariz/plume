"""Ports: stored release notes per build and what each package said about its extraction."""

from collections.abc import Mapping
from typing import Any, Protocol

from plume.domain.knowledge.release_notes import PackageMeta


class PackageMetaReader(Protocol):
    def read(self, ref: str) -> PackageMeta:
        """The package's extraction metadata (empty when it has none)."""
        ...


class ReleaseNotesRepo(Protocol):
    def save_meta(self, build_id: str, meta: Mapping[str, Any]) -> None:
        """Store (or replace) a build's package metadata."""
        ...

    def get_meta(self, build_id: str) -> dict[str, Any] | None: ...

    def save(self, notes: Mapping[str, Any]) -> None:
        """Store (or replace) the notes of ``notes['to']`` (from ``notes['from']``)."""
        ...

    def get(self, to_build: str) -> dict[str, Any] | None: ...

    def card_notes(self, to_builds: list[str]) -> dict[str, dict[str, Any]]:
        """For API cards: several builds' notes in one read, reduced to api, to, toDocsAsOf and
        each user-visible item's class / breaking / wordingOnly / kind (builds without notes are
        absent). A database may project them; returning the whole notes is also correct."""
        ...

    def for_api(self, api_id: str) -> list[dict[str, Any]]:
        """Every build's notes of an API, newest first."""
        ...
