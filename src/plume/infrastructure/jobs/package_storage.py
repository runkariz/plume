"""Uploaded package zips, stored and extracted safely under ``<data_dir>/jobs/<job id>/``."""

import io
import stat
import zipfile
from pathlib import Path, PurePosixPath

from plume.application.errors import SourcePackageError
from plume.application.ports.jobs import StoredPackage

MAX_FILES = 20_000
MAX_UNCOMPRESSED = 1024 * 1024 * 1024  # 1 GiB
MAX_RATIO = 200  # zip-bomb guard


class LocalPackageStorage:
    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self._root = root
        self._max_upload = max_upload_bytes

    def save(self, job_id: str, filename: str, data: bytes) -> StoredPackage:
        if len(data) > self._max_upload:
            raise SourcePackageError(f"package is larger than {self._max_upload} bytes")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise SourcePackageError("not a valid zip file") from exc
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) > MAX_FILES:
            raise SourcePackageError(f"too many files ({len(members)} > {MAX_FILES})")
        total = sum(m.file_size for m in members)
        if total > MAX_UNCOMPRESSED or (data and total / max(len(data), 1) > MAX_RATIO):
            raise SourcePackageError("the zip expands too much")
        target = self._root / "jobs" / job_id / "package"
        target.mkdir(parents=True, exist_ok=False)
        # The client's file name is only shown back (job.package.filename), never used as a path.
        (self._root / "jobs" / job_id / "upload.zip").write_bytes(data)
        for m in members:
            name = PurePosixPath(m.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise SourcePackageError(f"unsafe path in zip: {m.filename}")
            if stat.S_ISLNK(m.external_attr >> 16):
                raise SourcePackageError(f"symlink in zip: {m.filename}")
            dest = target.joinpath(*name.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(m) as src, dest.open("wb") as out:
                out.write(src.read(m.file_size + 1)[: m.file_size])
        return StoredPackage(
            path=str(_package_root(target)), files=len(members), size_bytes=len(data)
        )


def _package_root(target: Path) -> Path:
    """The folder that holds ``connector/app.json`` (zips often wrap one top folder)."""
    if (target / "connector" / "app.json").is_file() or (target / "app.json").is_file():
        return target
    for app in sorted(target.rglob("app.json")):
        if app.parent.name == "connector":
            return app.parent.parent
        return app.parent
    return target
