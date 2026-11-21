"""The real packages the gate's opt-in tests read (tests/real_packages.toml).

``real_packages(role)``: the role's package folders. An explicit ``PLUME_<ROLE>_PACKAGES`` wins.
Otherwise the pinned folders under the data directory (``PLUME_DATA_DIR``, default
``~/source/repos/plume-data``): all of them when every one is a package (has
connector/app.json), else none, so the tests skip. ``missing_pinned()`` lists the broken ones
for the one test that fails with a clear message (instead of a dozen errors deep in loading).
Without a data directory (CI) every real-package test skips, as before.
"""

import os
import tomllib
from pathlib import Path

CONFIG = Path(__file__).with_name("real_packages.toml")
ENV = {"suggest": "PLUME_SUGGEST_PACKAGES", "notes": "PLUME_NOTES_PACKAGES",
       "contract": "PLUME_CONTRACT_PACKAGES"}  # fmt: skip


def data_dir() -> Path:
    return Path(os.environ.get("PLUME_DATA_DIR") or "~/source/repos/plume-data").expanduser()


def pinned() -> dict[str, list[str]]:
    """Role -> pinned folder names, from the config file."""
    raw = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return {k: [str(v) for v in vs] for k, vs in raw.items() if isinstance(vs, list)}


def _is_package(path: Path) -> bool:
    return (path / "connector" / "app.json").is_file()


def missing_pinned() -> list[str]:
    """Pinned folders that are not packages under the data directory (none without one)."""
    base = data_dir()
    if not base.is_dir():
        return []
    names = sorted({n for ns in pinned().values() for n in ns})
    return [n for n in names if not _is_package(base / n)]


def real_packages(role: str) -> list[Path]:
    """The role's package folders, or [] (tests skip) when they are not all there."""
    explicit = os.environ.get(ENV[role], "")
    if explicit:
        return [Path(p) for p in explicit.split(os.pathsep) if p]
    base = data_dir()
    paths = [base / n for n in pinned()[role]]
    return paths if base.is_dir() and all(_is_package(p) for p in paths) else []
