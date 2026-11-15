"""``DumpStore`` on a local directory: ``<dir>/<api>/<build>.plume.jsonl.gz``."""

from pathlib import Path

from plume.application.errors import NotFoundError
from plume.application.ports.dump_store import BuildSnapshot
from plume.infrastructure.dumps.codec import decode, encode


class LocalDumpStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def encode(self, snapshot: BuildSnapshot) -> bytes:
        return encode(snapshot)

    def write(self, snapshot: BuildSnapshot, name: str | None = None) -> str:
        path = (
            Path(name)
            if name
            else self._root
            / snapshot.api.api_id.value
            / f"{snapshot.build.build_id.value}.plume.jsonl.gz"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(encode(snapshot))
        tmp.replace(path)
        return str(path)

    def read(self, ref: str) -> BuildSnapshot:
        path = Path(ref)
        if not path.is_file():
            raise NotFoundError(f"no dump at {ref}")
        return decode(path.read_bytes())
