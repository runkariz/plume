"""The gate's real packages: every pinned folder is there and pinned against the archive."""

import pytest

from tests.real_packages import data_dir, missing_pinned, pinned


def test_every_pinned_package_is_present() -> None:
    """One clear failure when the archive (or anything else) took a pinned folder; the real-
    package tests then skip instead of erroring one by one."""
    if not data_dir().is_dir():
        pytest.skip(f"no data directory {data_dir()} (set PLUME_DATA_DIR)")
    missing = missing_pinned()
    assert not missing, (
        f"pinned real packages missing or without connector/app.json under {data_dir()}: "
        f"{', '.join(missing)}. Restore them (they are listed in coord/PINNED) or update "
        "tests/real_packages.toml together with PINNED."
    )


def test_every_package_the_tests_read_is_pinned() -> None:
    pin_file = data_dir() / "coord" / "PINNED"
    if not pin_file.is_file():
        pytest.skip(f"no {pin_file}")
    listed = {ln.strip() for ln in pin_file.read_text().splitlines()
              if ln.strip() and not ln.startswith("#")}  # fmt: skip
    used = {n for ns in pinned().values() for n in ns}
    assert used <= listed, f"read by tests but not in {pin_file}: {sorted(used - listed)}"
