"""The package hash (part of the build identity) covers what the loader derived, so a loader
change makes a new build on reload; the same package and loader give the same hash."""

from pathlib import Path

import pytest

from plume.infrastructure.sources import stream_package
from plume.infrastructure.sources.stream_package import StreamPackageSource


@pytest.mark.parametrize("name", ["shopify-mini", "woo-mini", "mirakl-mini", "test-catalog"])
def test_the_same_package_hashes_the_same(packages: Path, name: str) -> None:
    source = StreamPackageSource()
    assert (
        source.load(str(packages / name)).package_hash
        == source.load(str(packages / name)).package_hash
    )


def test_a_loader_output_change_changes_the_hash(
    packages: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """d6ebb8b's webhook guides were a no-op on reload: same package, same build."""
    before = StreamPackageSource().load(str(packages / "shopify-mini")).package_hash
    monkeypatch.setattr(stream_package, "_webhook_document", lambda *_a: None)
    after = StreamPackageSource().load(str(packages / "shopify-mini")).package_hash
    assert before != after
