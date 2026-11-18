"""Gemini/Vertex adapter against recorded responses (httpx.MockTransport)."""

import json
import math
import threading
import time
from collections.abc import Callable

import httpx
import pytest

from plume.application.errors import EmbeddingError
from plume.infrastructure.embeddings.gemini import GeminiEmbedder

DIMS = 4
KEY = "test-key-not-real"


def _vertex_ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    preds = [
        {"embeddings": {"values": [3.0, 4.0, 0.0, 0.0], "statistics": {"token_count": 3}}}
        for _ in body["instances"]
    ]
    return httpx.Response(200, json={"predictions": preds})


def _gemini_ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        200, json={"embeddings": [{"values": [0.0, 2.0, 0.0, 0.0]} for _ in body["requests"]]}
    )


def _embedder(handler: Callable[[httpx.Request], httpx.Response], **kw: object) -> GeminiEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiEmbedder(KEY, dims=DIMS, client=client, sleep=lambda _s: None, **kw)  # type: ignore[arg-type]


def test_vertex_request_shape_and_normalisation() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _vertex_ok(request)

    emb = _embedder(handler, backend="vertex")
    vectors = emb.embed_documents(["a", "b"])
    assert vectors == [(0.6, 0.8, 0.0, 0.0)] * 2
    assert len(seen) == 2  # one instance per request on Vertex
    req = seen[0]
    assert req.url.path == "/v1/publishers/google/models/gemini-embedding-001:predict"
    assert "key" not in str(req.url.query)
    assert req.headers["x-goog-api-key"] == KEY
    body = json.loads(req.content)
    assert body["instances"] == [{"content": "a", "task_type": "RETRIEVAL_DOCUMENT"}]
    assert body["parameters"]["outputDimensionality"] == DIMS


def test_gemini_batches_and_query_task() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _gemini_ok(request)

    emb = _embedder(handler, backend="gemini", batch_size=2)
    assert len(emb.embed_documents(["a", "b", "c"])) == 3
    assert [len(b["requests"]) for b in seen] == [2, 1]  # type: ignore[arg-type]
    assert emb.embed_query("q") == (0.0, 1.0, 0.0, 0.0)
    assert seen[-1]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"  # type: ignore[index]


def test_retries_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": "quota"})
        return _vertex_ok(request)

    emb = _embedder(handler)
    assert math.isclose(sum(x * x for x in emb.embed_query("x")), 1.0)
    assert calls["n"] == 3


def test_gives_up_after_retries() -> None:
    emb = _embedder(lambda r: httpx.Response(503, text="busy"), max_retries=2)
    with pytest.raises(EmbeddingError, match="503"):
        emb.embed_query("x")


def test_client_error_is_not_retried_and_key_not_echoed() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(EmbeddingError) as info:
        _embedder(handler).embed_query("x")
    assert calls["n"] == 1
    assert KEY not in str(info.value)


def test_wrong_dims_or_count_is_an_error() -> None:
    emb = _embedder(
        lambda r: httpx.Response(200, json={"predictions": [{"embeddings": {"values": [1.0]}}]})
    )
    with pytest.raises(EmbeddingError, match="dims"):
        emb.embed_query("x")
    emb = _embedder(lambda r: httpx.Response(200, json={"predictions": []}))
    with pytest.raises(EmbeddingError, match="expected 1"):
        emb.embed_query("x")


def test_transport_error_retried_then_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(EmbeddingError, match="ConnectError"):
        _embedder(handler, max_retries=1).embed_query("x")


def test_key_required() -> None:
    with pytest.raises(EmbeddingError):
        GeminiEmbedder("")


def test_vertex_requests_run_in_parallel_and_keep_order() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        text = json.loads(request.content)["instances"][0]["content"]
        with lock:
            active -= 1
        n = float(int(text))
        return httpx.Response(
            200, json={"predictions": [{"embeddings": {"values": [n + 1, 0.0, 0.0, 0.0]}}]}
        )

    emb = _embedder(handler, backend="vertex", concurrency=4)
    texts = [str(i) for i in range(12)]
    vectors = emb.embed_documents(texts)
    assert vectors == [(1.0, 0.0, 0.0, 0.0)] * 12  # normalised, one per text, in order
    assert peak > 1
    assert peak <= 4


def test_parallel_keeps_the_order_of_distinct_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        i = int(json.loads(request.content)["instances"][0]["content"])
        values = [0.0, 0.0, 0.0, 0.0]
        values[i % 4] = 1.0
        return httpx.Response(200, json={"predictions": [{"embeddings": {"values": values}}]})

    emb = _embedder(handler, backend="vertex", concurrency=3)
    vectors = emb.embed_documents([str(i) for i in range(8)])
    assert [v.index(1.0) for v in vectors] == [i % 4 for i in range(8)]
