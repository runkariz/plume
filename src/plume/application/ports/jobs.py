"""Ports for maintainer jobs: job records, their event log, package storage, a runner."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

JsonObj = dict[str, Any]


class JobStatus(StrEnum):
    UPLOADED = "uploaded"
    REVIEWED = "reviewed"
    BUILDING = "building"
    STAGED = "staged"
    FAILED = "failed"
    PUBLISHED = "published"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    status: JobStatus
    package_path: str
    package: Mapping[str, Any]  # PackageInfo: filename, sizeBytes, files, contents, validation...
    api_id: str | None = None
    display_name: str | None = None
    tag: str = "latest"
    diff: Mapping[str, Any] | None = None
    plan: Mapping[str, Any] | None = None
    eval: Mapping[str, Any] | None = None
    live_build: str | None = None
    staged_build: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = field(default=None, compare=False)


class JobRepo(Protocol):
    def create(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def save(self, job: Job) -> None: ...

    def compare_and_set(self, job_id: str, expected: set[JobStatus], new: Job) -> bool:
        """Save ``new`` only if the stored status is in ``expected`` (atomic)."""
        ...


@dataclass(frozen=True, slots=True)
class StoredEvent:
    seq: int
    payload: JsonObj


class JobEventLog(Protocol):
    def append(self, job_id: str, payload: JsonObj) -> int: ...

    def after(self, job_id: str, seq: int, limit: int = 500) -> list[StoredEvent]: ...


@dataclass(frozen=True, slots=True)
class StoredPackage:
    path: str  # directory that contains connector/
    files: int
    size_bytes: int


class PackageStorage(Protocol):
    def save(self, job_id: str, filename: str, data: bytes) -> StoredPackage:
        """Store and safely extract an uploaded zip. Raises ``SourcePackageError``."""
        ...


class JobRunner(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...
