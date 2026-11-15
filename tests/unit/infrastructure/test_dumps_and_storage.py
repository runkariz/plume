import gzip
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from plume.application.errors import NotFoundError, SourcePackageError
from plume.infrastructure.dumps.codec import DumpFormatError, decode, encode
from plume.infrastructure.dumps.local_fs import LocalDumpStore
from plume.infrastructure.jobs.package_storage import LocalPackageStorage
from plume.infrastructure.sources.gold_file import JsonGoldSource
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack


def _snapshot(packages: Path, tmp: Path):  # type: ignore[no-untyped-def]
    stack = FakeStack(embedder=WordEmbedder(), data_dir=tmp)
    build = stack.pipeline().execute("j", str(packages / "test-catalog")).build_id
    return stack.export().snapshot(build)


def test_codec_round_trip_and_determinism(packages: Path, tmp_path: Path) -> None:
    snap = _snapshot(packages, tmp_path)
    data = encode(snap)
    assert data == encode(snap)
    back = decode(data)
    assert back.build == snap.build
    assert back.api == snap.api
    assert sorted(back.documents, key=lambda d: d.doc_id) == sorted(
        snap.documents, key=lambda d: d.doc_id
    )
    assert set(back.facts) == set(snap.facts)
    assert back.vectors.keys() == snap.vectors.keys()
    first = gzip.decompress(data).split(b"\n")[0]
    assert json.loads(first)["format"] == "plume-dump"


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"not gzip", "gzip"),
        (gzip.compress(b'{"type": "x"}'), "not a plume dump"),
        (gzip.compress(b'{"type":"manifest","format":"plume-dump","version":9}'), "version"),
        (gzip.compress(b"{bad"), "manifest"),
    ],
)
def test_codec_rejects_bad_dumps(data: bytes, match: str) -> None:
    with pytest.raises(DumpFormatError, match=match):
        decode(data)


def test_codec_checks_counts(packages: Path, tmp_path: Path) -> None:
    lines = gzip.decompress(encode(_snapshot(packages, tmp_path))).splitlines()
    with pytest.raises(DumpFormatError, match="counts"):
        decode(gzip.compress(b"\n".join(lines[:-1])))


def test_local_store(packages: Path, tmp_path: Path) -> None:
    store = LocalDumpStore(tmp_path / "d")
    ref = store.write(_snapshot(packages, tmp_path))
    assert Path(ref).is_file()
    assert store.read(ref).build.is_sealed
    with pytest.raises(NotFoundError):
        store.read(str(tmp_path / "missing.gz"))


def test_gold_file(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text(
        json.dumps({"api": "x", "questions": [{"id": "a", "kind": "absent", "name": "n"}]})
    )
    src = JsonGoldSource([tmp_path])
    assert src.for_api("x") == str(tmp_path / "x.json")
    assert src.for_api("y") is None
    gold, digest = src.load(str(tmp_path / "x.json"))
    assert gold.questions[0].fact_name == "n"
    assert digest.startswith("sha256:")
    (tmp_path / "bad.json").write_text('{"api": "x", "questions": []}')
    with pytest.raises(SourcePackageError, match="invalid gold set"):
        src.load(str(tmp_path / "bad.json"))


def _zip(entries: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def zip_dir(root: Path, prefix: str = "") -> bytes:
    return _zip(
        {prefix + str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    )


def test_package_storage_extracts_and_finds_root(packages: Path, tmp_path: Path) -> None:
    storage = LocalPackageStorage(tmp_path, 10_000_000)
    stored = storage.save("job-1", "p.zip", zip_dir(packages / "test-catalog", "wrapped/"))
    assert (Path(stored.path) / "connector" / "app.json").is_file()
    assert stored.files > 10


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"nope", "valid zip"),
        (_zip({"../evil": b"x"}), "unsafe path"),
        (_zip({"/abs": b"x"}), "unsafe path"),
        (_zip({}, symlink="link"), "symlink"),
        (_zip({"big": b"0" * 3_000_000}), "expands"),
    ],
)
def test_package_storage_rejects_unsafe_zips(tmp_path: Path, data: bytes, match: str) -> None:
    with pytest.raises(SourcePackageError, match=match):
        LocalPackageStorage(tmp_path, 10_000_000).save("job-x", "p.zip", data)


def test_package_storage_size_limit(tmp_path: Path) -> None:
    with pytest.raises(SourcePackageError, match="larger"):
        LocalPackageStorage(tmp_path, 10).save("job-y", "p.zip", b"0" * 11)


def test_codec_carries_assets_raw_and_tags(packages: Path, tmp_path: Path) -> None:
    stack = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    build = stack.pipeline().execute("j", str(packages / "shopify-mini")).build_id
    snap = stack.export().snapshot(build)
    assert [a.name for a in snap.assets] == ["icon"]
    back = decode(encode(snap))
    assert back.assets == snap.assets
    trig = next(d for d in back.documents if d.kind.value == "trigger")
    assert trig.raw is not None
    assert trig.raw["delivery"] == "webhook"
    ep = next(d for d in back.documents if d.kind.value == "endpoint")
    assert ep.tags
