"""Gemini embeddings over HTTP: the Gemini API (AI Studio key) or Vertex AI express mode.

- ``gemini``: ``POST generativelanguage.googleapis.com/v1beta/models/<model>:batchEmbedContents``
- ``vertex``: ``POST aiplatform.googleapis.com/v1/publishers/google/models/<model>:predict``

Both take the key in the ``x-goog-api-key`` header (never in the URL, so it can't reach logs).
Vectors are requested at ``dims`` and re-normalised to unit length (reduced-size Gemini
embeddings are not normalised). 429 and 5xx are retried with exponential backoff.
"""

import math
import time
from collections.abc import Callable, Sequence
from typing import Any, Literal

import httpx

from plume.application.errors import EmbeddingError
from plume.application.ports.embedder import Vector

Backend = Literal["gemini", "vertex"]
TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
VERTEX_URL = "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:predict"
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _normalize(values: Sequence[float]) -> Vector:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0 or not math.isfinite(norm):
        raise EmbeddingError("embedding is zero or not finite")
    return tuple(v / norm for v in values)


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str,
        backend: Backend = "vertex",
        model: str = "gemini-embedding-001",
        dims: int = 768,
        batch_size: int | None = None,
        max_retries: int = 5,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise EmbeddingError("an API key is required for the Gemini embedder")
        self._key = api_key
        self._backend = backend
        self._model = model
        self._dims = dims
        # Vertex's gemini-embedding-001 takes one instance per request.
        self._batch = batch_size or (1 if backend == "vertex" else 100)
        self._retries = max_retries
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep
        self.requests = 0

    @property
    def model(self) -> str:
        return self._model

    @property
    def dims(self) -> int:
        return self._dims

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(self._retries + 1):
            self.requests += 1
            try:
                response = self._client.post(url, json=body, headers={"x-goog-api-key": self._key})
            except httpx.TransportError as exc:
                if attempt == self._retries:
                    raise EmbeddingError(
                        f"{self._backend} request failed: {type(exc).__name__}"
                    ) from exc
                self._sleep(delay)
                delay *= 2
                continue
            if response.status_code in _RETRY_STATUS and attempt < self._retries:
                retry_after = response.headers.get("retry-after")
                self._sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
                delay *= 2
                continue
            if response.status_code != 200:
                raise EmbeddingError(
                    f"{self._backend} embeddings returned HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
            data = response.json()
            if not isinstance(data, dict):
                raise EmbeddingError("unexpected embeddings response")
            return data
        raise EmbeddingError("retries exhausted")  # pragma: no cover

    def _embed_batch(self, texts: Sequence[str], task: TaskType) -> list[Vector]:
        if self._backend == "gemini":
            data = self._post(
                GEMINI_URL.format(model=self._model),
                {
                    "requests": [
                        {
                            "model": f"models/{self._model}",
                            "content": {"parts": [{"text": t}]},
                            "taskType": task,
                            "outputDimensionality": self._dims,
                        }
                        for t in texts
                    ]
                },
            )
            raw = [e.get("values") for e in data.get("embeddings", [])]
        else:
            data = self._post(
                VERTEX_URL.format(model=self._model),
                {
                    "instances": [{"content": t, "task_type": task} for t in texts],
                    "parameters": {"outputDimensionality": self._dims, "autoTruncate": True},
                },
            )
            raw = [p.get("embeddings", {}).get("values") for p in data.get("predictions", [])]
        if len(raw) != len(texts) or any(not isinstance(v, list) for v in raw):
            raise EmbeddingError(f"expected {len(texts)} embeddings, got {len(raw)}")
        vectors = [_normalize([float(x) for x in v]) for v in raw if isinstance(v, list)]
        for v in vectors:
            if len(v) != self._dims:
                raise EmbeddingError(f"got {len(v)} dims, expected {self._dims}")
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        out: list[Vector] = []
        for start in range(0, len(texts), self._batch):
            out.extend(self._embed_batch(texts[start : start + self._batch], "RETRIEVAL_DOCUMENT"))
        return out

    def embed_query(self, text: str) -> Vector:
        return self._embed_batch([text], "RETRIEVAL_QUERY")[0]
