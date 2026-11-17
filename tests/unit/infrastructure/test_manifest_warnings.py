"""manifest.json warnings are kept on the app document and count in the package hash; a
package without them hashes as before."""

import json
import shutil
from pathlib import Path

from plume.domain.knowledge.document import DocumentKind
from plume.infrastructure.sources.stream_package import StreamPackageSource

source = StreamPackageSource()
WARNINGS = [
    'auth-requires-signature: shop-key "All requests must contain a Shop-Signature"',
    "default-environment-by-order: production",
    "knowledge-links: 3 units with endpointId",
]


def warned_package(packages: Path, tmp_path: Path, warnings: list[str] = WARNINGS) -> Path:
    dst = tmp_path / "shopify-warned"
    shutil.copytree(packages / "shopify-mini", dst)
    manifest = dst / "manifest.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "warnings": warnings}))
    return dst


def test_warnings_are_kept_on_the_app_document(packages: Path, tmp_path: Path) -> None:
    package = source.load(str(warned_package(packages, tmp_path)))
    app = next(d for d in package.documents if d.kind is DocumentKind.APP)
    assert (app.raw or {})["package_warnings"] == WARNINGS


def test_only_the_warnings_of_the_manifest_count_in_the_hash(
    packages: Path, tmp_path: Path
) -> None:
    plain = source.load(str(packages / "shopify-mini")).package_hash
    root = warned_package(packages, tmp_path)
    warned = source.load(str(root)).package_hash
    assert warned != plain
    manifest = root / "manifest.json"
    data = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**data, "runId": "r_other"}))
    assert source.load(str(root)).package_hash == warned  # a new run id alone: same bytes
    manifest.write_text(json.dumps({**data, "warnings": []}))
    assert source.load(str(root)).package_hash == plain
