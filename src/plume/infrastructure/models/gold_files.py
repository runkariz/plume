"""Model gold from JSON files (``plume.model-gold.v1``) in the configured dirs."""

import json
from pathlib import Path

from plume.application.errors import NotFoundError
from plume.domain.models.model_gold import GoldModel, parse_gold
from plume.domain.models.set_gold import SET_SCHEMA, SetGold, parse_set_gold


class JsonModelGold:
    def __init__(self, dirs: tuple[Path, ...] = ()) -> None:
        self._dirs = dirs

    def _raw(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read(self, path: Path) -> tuple[GoldModel, ...]:
        raw = self._raw(path)
        if isinstance(raw, dict) and raw.get("schema") == SET_SCHEMA:
            return ()  # a set gold: its relations are scored by sets()
        return parse_gold(raw, path.name)

    def _path(self, ref: str) -> Path:
        path = Path(ref).expanduser()
        if path.is_file():
            return path
        for folder in self._dirs:
            candidate = folder / Path(ref).name  # a file name inside a gold dir
            if candidate.is_file():
                return candidate
        raise NotFoundError(f"model gold {ref} not found")

    def load(self, ref: str) -> tuple[GoldModel, ...]:
        return self._read(self._path(ref))

    def _files(self) -> list[Path]:
        return [p for d in self._dirs if d.is_dir() for p in sorted(d.glob("*.json"))]

    def all(self) -> tuple[GoldModel, ...]:
        return tuple(m for path in self._files() for m in self._read(path))

    def _set(self, path: Path) -> tuple[SetGold, ...]:
        raw = self._raw(path)
        if isinstance(raw, dict) and raw.get("schema") == SET_SCHEMA:
            return (parse_set_gold(raw, path.name),)
        return ()

    def sets(self) -> tuple[SetGold, ...]:
        return tuple(g for path in self._files() for g in self._set(path))

    def load_sets(self, ref: str) -> tuple[SetGold, ...]:
        return self._set(self._path(ref))
