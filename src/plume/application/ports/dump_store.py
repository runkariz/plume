"""Ports: build snapshots, the dump codec/store, and the atomic restore."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from plume.application.ports.embedder import Vector
from plume.application.ports.eval_repo import EvalRecord
from plume.domain.knowledge.api import ApiInfo
from plume.domain.knowledge.asset import Asset
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.document import Document
from plume.domain.knowledge.fact import Fact
from plume.domain.shared.ids import BuildId

DUMP_FORMAT = "plume-dump"
DUMP_VERSION = 1


@dataclass(frozen=True, slots=True)
class BuildSnapshot:
    """Everything a sealed build is: enough to restore it anywhere, byte for byte."""

    api: ApiInfo
    build: Build
    documents: tuple[Document, ...]
    chunks: tuple[Chunk, ...]
    vectors: Mapping[str, Vector]
    facts: tuple[Fact, ...]
    eval: EvalRecord | None = None
    assets: tuple[Asset, ...] = ()
    # Release notes of this build (against its predecessor) and what its package said about
    # the extraction: carried so prod shows the same notes without recomputing them.
    release_notes: Mapping[str, Any] | None = None
    package_meta: Mapping[str, Any] | None = None


class DumpStore(Protocol):
    def write(self, snapshot: BuildSnapshot, name: str | None = None) -> str:
        """Write a dump; returns its reference (path or URL)."""
        ...

    def read(self, ref: str) -> BuildSnapshot: ...

    def encode(self, snapshot: BuildSnapshot) -> bytes:
        """The dump bytes (gzip), deterministic for the same snapshot."""
        ...


class VectorReader(Protocol):
    def vectors_of(self, build_id: BuildId) -> dict[str, Vector]: ...


class BuildImporter(Protocol):
    def restore(self, snapshot: BuildSnapshot, tags: Sequence[str] = ()) -> None:
        """Insert the snapshot in one transaction (all or nothing). Fails if the build exists."""
        ...

    def exists(self, build_id: BuildId) -> bool: ...
