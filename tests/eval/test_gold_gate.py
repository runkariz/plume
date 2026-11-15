"""The release gate on the gold sets (`make eval`).

Offline by default (word-hash embedder, in-memory stores): every fixture package with a gold set
passes, and a damaged package is stopped. With PLUME_EVAL_LIVE=1 and a key, the same runs use
the configured live embedder (Level 2); point PLUME_EVAL_PACKAGES at real packages as
``api=path`` pairs separated by os.pathsep.
"""

import os
import shutil
from pathlib import Path

import pytest

from plume.application.ports.embedder import Embedder
from plume.infrastructure.settings import Settings
from plume.infrastructure.sources.gold_file import JsonGoldSource
from tests.fakes.knowledge import DeterministicEmbedder, WordEmbedder
from tests.fakes.stack import FakeStack

pytestmark = pytest.mark.eval
ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "fixtures" / "gold"
PACKAGES = ROOT / "fixtures" / "packages"
FIXTURES = {
    "test-catalog-api": "test-catalog",
    "second-catalog-api": "second-catalog",
    "shopify": "shopify-mini",
}


def _extra() -> dict[str, Path]:
    pairs = [p for p in os.environ.get("PLUME_EVAL_PACKAGES", "").split(os.pathsep) if "=" in p]
    return {k: Path(v) for k, v in (p.split("=", 1) for p in pairs)}


def _embedder() -> DeterministicEmbedder | Embedder:
    if os.environ.get("PLUME_EVAL_LIVE") != "1":
        return WordEmbedder()
    from plume.bootstrap.container import Container  # noqa: PLC0415

    settings = Settings()
    if settings.resolved_embedder == "hash":
        pytest.skip("PLUME_EVAL_LIVE=1 needs PLUME_VERTEX_API_KEY or PLUME_GEMINI_API_KEY")
    return Container(settings=settings).embedder


def _stack(tmp: Path) -> FakeStack:
    return FakeStack(embedder=_embedder(), gold=JsonGoldSource([GOLD]), data_dir=tmp)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("api", "path"),
    [(a, PACKAGES / p) for a, p in FIXTURES.items()] + list(_extra().items()),
    ids=lambda x: str(x) if isinstance(x, str) else x.name,
)
def test_gold_set_passes(api: str, path: Path, tmp_path: Path) -> None:
    result = _stack(tmp_path).pipeline().execute("eval", str(path))
    assert result.api_id.value == api
    assert result.gate is not None, f"no gold set for {api}"
    print(f"{api}: {result.gate.metrics}")
    assert result.gate.passed, result.gate.message


def test_damaged_package_is_stopped(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    assert stack.pipeline().execute("e1", str(PACKAGES / "test-catalog")).gate.passed  # type: ignore[union-attr]
    damaged = tmp_path / "damaged"
    shutil.copytree(PACKAGES / "test-catalog", damaged)
    shutil.rmtree(damaged / "connector" / "endpoints" / "get-api-v1-orders")
    result = stack.pipeline().execute("e2", str(damaged))
    assert result.gate is not None
    assert not result.gate.passed
    assert result.tag is None
