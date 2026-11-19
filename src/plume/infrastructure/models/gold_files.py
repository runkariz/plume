"""Model gold from JSON files (``plume.model-gold.v1``) in the configured dirs."""

import json
from pathlib import Path

from plume.application.errors import NotFoundError
from plume.domain.models.model_gold import GoldModel, parse_gold


class JsonModelGold:
    def __init__(self, dirs: tuple[Path, ...] = ()) -> None:
        self._dirs = dirs

    def _read(self, path: Path) -> tuple[GoldModel, ...]:
        return parse_gold(json.loads(path.read_text(encoding="utf-8")), path.name)

    def load(self, ref: str) -> tuple[GoldModel, ...]:
        path = Path(ref).expanduser()
        if path.is_file():
            return self._read(path)
        for folder in self._dirs:
            candidate = folder / Path(ref).name  # a file name inside a gold dir
            if candidate.is_file():
                return self._read(candidate)
        raise NotFoundError(f"model gold {ref} not found")

    def all(self) -> tuple[GoldModel, ...]:
        out: list[GoldModel] = []
        for folder in self._dirs:
            for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
                out.extend(self._read(path))
        return tuple(out)
