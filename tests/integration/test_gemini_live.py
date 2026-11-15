"""Live embeddings (Vertex express or Gemini API). Runs only with a key: `make e2e-live`.

Skips without PLUME_VERTEX_API_KEY / PLUME_GEMINI_API_KEY. The key is read by Settings and never
printed.
"""

import math

import pytest

from plume.infrastructure.embeddings.gemini import GeminiEmbedder
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.live


def _embedder() -> GeminiEmbedder:
    settings = Settings()
    kind = settings.resolved_embedder
    if kind == "hash":
        pytest.skip("no PLUME_VERTEX_API_KEY or PLUME_GEMINI_API_KEY")
    key = settings.vertex_api_key if kind == "vertex" else settings.gemini_api_key
    assert key is not None
    return GeminiEmbedder(key.get_secret_value(), backend=kind, model=settings.embed_model)


def test_live_embeddings_rank_the_related_text_first() -> None:
    emb = _embedder()
    docs = emb.embed_documents(
        [
            "Retrieve a list of products in the store catalog.",
            "Cancel an order before it is fulfilled.",
            "Rate limits: a leaky bucket of 40 requests per app per store.",
        ]
    )
    assert all(len(v) == 768 for v in docs)
    assert all(math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-6) for v in docs)
    query = emb.embed_query("how do I list products?")
    scores = [sum(a * b for a, b in zip(query, d, strict=True)) for d in docs]
    assert scores.index(max(scores)) == 0
