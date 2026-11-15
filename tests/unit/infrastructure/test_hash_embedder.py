import math

from plume.infrastructure.embeddings.hash_embedder import HashEmbedder


def _cos(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_unit_length_deterministic_and_word_sensitive() -> None:
    emb = HashEmbedder(64)
    a = emb.embed_query("list the shop orders")
    assert math.isclose(sum(x * x for x in a), 1.0)
    assert a == emb.embed_documents(["list the shop orders"])[0]
    close = emb.embed_query("orders of the shop list")
    far = emb.embed_query("refund payment dispute evidence")
    assert _cos(a, close) > _cos(a, far)
    assert emb.embed_query("") != ()
