"""Deterministic, offline embedder (feature hashing of word unigrams and bigrams).

Not semantic, but texts that share words get close vectors, which is enough for local runs, CI
and the e2e suite without any API key. Model name: ``plume-hash-v1``.
"""

import hashlib
import itertools
import math
import re
from collections.abc import Sequence

from plume.application.ports.embedder import Vector

_WORD = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    def __init__(self, dims: int = 768) -> None:
        self._dims = dims

    @property
    def model(self) -> str:
        return "plume-hash-v1"

    @property
    def dims(self) -> int:
        return self._dims

    def _embed(self, text: str) -> Vector:
        words = _WORD.findall(text.lower())
        features = words + [f"{a}_{b}" for a, b in itertools.pairwise(words)]
        values = [0.0] * self._dims
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dims
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0:
            values[0], norm = 1.0, 1.0
        return tuple(v / norm for v in values)

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> Vector:
        return self._embed(text)
