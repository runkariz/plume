"""Port: read an input package (a stream/connector package or any producer's equivalent)."""

from dataclasses import dataclass
from typing import Protocol

from plume.domain.knowledge.api import ApiInfo
from plume.domain.knowledge.asset import Asset
from plume.domain.knowledge.document import Document


@dataclass(frozen=True, slots=True)
class SourcePackage:
    api: ApiInfo
    documents: tuple[Document, ...]
    package_hash: str
    source_ref: str
    run_id: str | None = None
    contract_version: str | None = None
    warnings: tuple[str, ...] = ()
    assets: tuple[Asset, ...] = ()


class PackageSource(Protocol):
    def load(self, ref: str) -> SourcePackage:
        """Read the package at ``ref``. Raises ``SourcePackageError`` when it is unusable."""
        ...
