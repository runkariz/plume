"""The maintainer's API display name: override > package title > derived; per API, not per
build; survives reloads; null clears it."""

import json
import shutil
from pathlib import Path

import pytest

from plume.application.errors import NotFoundError
from plume.application.knowledge.api_display import DisplayNameError
from tests.fakes.stack import FakeStack

API = "test-catalog-api"


def _name(s: FakeStack) -> tuple[str, str]:
    o = s.overviews().one(API, None)
    return o.info.display_name, o.info.display_source


def test_override_wins_and_survives_reloads(packages: Path) -> None:
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    derived = _name(s)  # the package name (no override)
    assert derived[1] == "package"  # name "Test Catalog API" differs from systemName
    out = s.api_display().set(API, "Test Catalog")
    assert out == {"api": API, "name": "Test Catalog", "nameSource": "override",
                   "packageName": derived[0]}  # fmt: skip
    s.load(str(packages / "test-catalog"))
    assert _name(s) == ("Test Catalog", "override")
    s.api_display().set(API, None)
    assert _name(s) == derived


def test_package_title_beats_the_derived_name(packages: Path, tmp_path: Path) -> None:
    copy = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", copy)
    app = copy / "connector" / "app.json"
    data = json.loads(app.read_text())
    data["title"] = "Test Catalog (package)"
    app.write_text(json.dumps(data))
    s = FakeStack()
    s.load(str(copy))
    assert _name(s) == ("Test Catalog (package)", "package")
    s.api_display().set(API, "Mine")
    assert _name(s) == ("Mine", "override")


def test_bad_input(packages: Path) -> None:
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    with pytest.raises(NotFoundError):
        s.api_display().set("nope", "X")
    for bad in ("   ", "x" * 81):
        with pytest.raises(DisplayNameError):
            s.api_display().set(API, bad)
