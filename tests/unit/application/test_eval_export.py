import gzip
import json
import shutil
from pathlib import Path

import pytest

from plume.application.errors import GateFailedError, IncompleteBuildError
from plume.application.knowledge.export_dump import DumpIntegrityError
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import TagName
from plume.domain.shared.ids import BuildId
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

GOLD = Path(__file__).resolve().parents[2] / "fixtures" / "gold"
CATALOG = ApiId("test-catalog-api")


def _damaged(packages: Path, tmp: Path) -> Path:
    copy = tmp / "damaged"
    shutil.copytree(packages / "test-catalog", copy)
    shutil.rmtree(copy / "connector" / "endpoints" / "get-api-v1-orders")
    return copy


def _stack(tmp_path: Path) -> FakeStack:
    from plume.infrastructure.sources.gold_file import JsonGoldSource  # noqa: PLC0415

    return FakeStack(embedder=WordEmbedder(), gold=JsonGoldSource([GOLD]), data_dir=tmp_path)


def test_gate_passes_and_tags(packages: Path, tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    r = stack.pipeline().execute("j", str(packages / "test-catalog"))
    assert r.gate is not None
    assert r.gate.passed, r.gate.message
    assert r.gate.metrics["recall_at_k"] == 1.0
    assert r.tag is not None
    record = stack.evals.get(r.build_id)
    assert record is not None
    assert record.passed
    assert len(record.details) == 8


def test_damaged_package_is_stopped(packages: Path, tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    good = stack.pipeline().execute("j1", str(packages / "test-catalog"))
    bad = stack.pipeline().execute("j2", str(_damaged(packages, tmp_path)))
    assert bad.gate is not None
    assert not bad.gate.passed
    assert "missing" in bad.gate.message
    assert bad.gate.baseline == good.build_id.value
    assert bad.tag is None
    assert stack.tags.get(CATALOG, TagName("latest")).build_id == good.build_id  # type: ignore[union-attr]
    assert ("tag", "skipped") in stack.events.steps()
    with pytest.raises(GateFailedError):
        stack.tag().execute(bad.build_id, "latest")
    forced = stack.tag().execute(bad.build_id, "latest", force=True)
    assert forced.previous == good.build_id


def test_explicit_gold_ref_and_no_gold(packages: Path, tmp_path: Path) -> None:
    stack = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    r = stack.pipeline().execute("j", str(packages / "test-catalog"))
    assert r.gate is None
    assert ("evaluate", "skipped") in stack.events.steps()
    r2 = stack.pipeline().execute(
        "j2", str(packages / "test-catalog"), gold_ref=str(GOLD / "test-catalog-api.json")
    )
    assert r2.gate is not None
    assert r2.gate.passed


def test_export_restore_round_trip(packages: Path, tmp_path: Path) -> None:
    src = _stack(tmp_path / "a")
    built = src.pipeline().execute("j", str(packages / "shopify-mini"))
    ref = src.export().execute(built.build_id)
    assert ref.endswith(f"{built.build_id}.plume.jsonl.gz")
    assert src.export().bytes(built.build_id) == Path(ref).read_bytes()  # deterministic

    dst = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path / "a")
    result = dst.restore().execute(ref, ["latest"])
    assert result.restored
    assert result.tags == ("latest",)
    assert dst.restore().execute(ref).restored is False  # idempotent

    q = "assigned fulfillment orders"
    a = src.search().execute("shopify", q)
    b = dst.search().execute("shopify", q)
    assert [h.doc_id for h in a.hits] == [h.doc_id for h in b.hits]
    fa = src.find_fact().execute("shopify", "since_id")
    fb = dst.find_fact().execute("shopify", "since_id")
    assert fa.matches == fb.matches
    assert dst.evals.get(built.build_id) == src.evals.get(built.build_id)


def _rewrite(path: Path, edit: object) -> None:
    lines = [json.loads(x) for x in gzip.decompress(path.read_bytes()).splitlines() if x]
    edit(lines)  # type: ignore[operator]
    path.write_bytes(gzip.compress(b"\n".join(json.dumps(x).encode() for x in lines)))


def test_tampered_dump_is_refused(packages: Path, tmp_path: Path) -> None:
    src = _stack(tmp_path)
    built = src.pipeline().execute("j", str(packages / "test-catalog"))
    ref = Path(src.export().execute(built.build_id))

    def change_text(lines: list[dict[str, object]]) -> None:
        chunk = next(x for x in lines if x["type"] == "chunk")
        chunk["text"] = str(chunk["text"]) + " (edited)"

    _rewrite(ref, change_text)
    dst = FakeStack(data_dir=tmp_path)
    with pytest.raises(DumpIntegrityError, match="items"):
        dst.restore().execute(str(ref))
    assert dst.builds.get(built.build_id) is None


def test_draft_cannot_be_exported(packages: Path, tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    imported = stack.import_package().execute(str(packages / "test-catalog"))
    with pytest.raises(IncompleteBuildError):
        stack.export().execute(imported.build_id)
    with pytest.raises(Exception, match="not found"):
        stack.export().execute(BuildId.new())
