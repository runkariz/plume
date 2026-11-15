"""The Vertex key from a mounted file (no key in a container's env) and per-embedder gate floors."""

from pathlib import Path

from plume.infrastructure.settings import Settings


def test_vertex_key_from_file_selects_vertex(tmp_path: Path) -> None:
    key = tmp_path / "vertex-api-key"
    key.write_text("from-file-0123456789\n")
    s = Settings(embedder="auto", vertex_key_file=key)
    assert s.vertex_key() == "from-file-0123456789"
    assert s.resolved_embedder == "vertex"
    assert "from-file" not in repr(s)  # never rendered
    env_wins = Settings(embedder="auto", vertex_key_file=key, vertex_api_key="from-env-0123456789")
    assert env_wins.vertex_key() == "from-env-0123456789"
    missing = Settings(embedder="auto", vertex_key_file=tmp_path / "nope")
    assert missing.vertex_key() is None
    assert missing.resolved_embedder == "hash"


def test_gate_floor_per_embedder(tmp_path: Path) -> None:
    assert Settings(embedder="hash").gate_floor() == 0.6
    tuned = {"vertex": 0.75}
    assert Settings(embedder="hash", gate_min_recall_by_embedder=tuned).gate_floor() == 0.6
    key = tmp_path / "k"
    key.write_text("k-0123456789")
    vertex = Settings(embedder="vertex", vertex_key_file=key, gate_min_recall_by_embedder=tuned)
    assert vertex.gate_floor() == 0.75
    assert Settings(embedder="vertex", vertex_key_file=key).gate_floor() == 0.6  # default kept
