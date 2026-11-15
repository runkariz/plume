"""Gemini on Vertex AI express mode (generateContent) as the server-side model writer.

The key is read from a file on every call (so it can be rotated without a restart) and sent only
in the ``x-goog-api-key`` header: never in a URL, a log line or an error message.
"""

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from plume.application.ports.model_writer import (
    ModelWriterError,
    ModelWriterUnavailableError,
    Turn,
)

VERTEX_GENERATE_URL = (
    "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"
)
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class VertexGeminiWriter:
    def __init__(
        self,
        key_file: Path | None,
        model: str = "gemini-4-argon",
        max_retries: int = 4,
        timeout: float = 300.0,
        max_output_tokens: int = 32_768,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._key_file = key_file
        self._model = model
        self._retries = max_retries
        self._max_tokens = max_output_tokens
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    def available(self) -> bool:
        return self._key_file is not None and self._key_file.is_file()

    def _key(self) -> str:
        if self._key_file is None:
            raise ModelWriterUnavailableError("server-side generation is not configured")
        try:
            key = self._key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ModelWriterUnavailableError("the LLM key file cannot be read") from exc
        if not key:
            raise ModelWriterUnavailableError("the LLM key file is empty")
        return key

    def write(self, system: str, turns: Sequence[Turn]) -> str:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": t.role, "parts": [{"text": t.text}]} for t in turns],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": self._max_tokens,
            },
        }
        url = VERTEX_GENERATE_URL.format(model=self._model)
        delay = 2.0
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(
                    url, json=body, headers={"x-goog-api-key": self._key()}
                )
            except httpx.TransportError as exc:
                if attempt == self._retries:
                    raise ModelWriterError(f"LLM request failed: {type(exc).__name__}") from exc
                self._sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if response.status_code in _RETRY_STATUS and attempt < self._retries:
                self._sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if response.status_code in (401, 403):
                raise ModelWriterUnavailableError(
                    f"the LLM refused the key (HTTP {response.status_code})"
                )
            if response.status_code != 200:
                raise ModelWriterError(f"LLM HTTP {response.status_code}")
            return _text(response.json())
        raise ModelWriterError("LLM retries exhausted")  # pragma: no cover


def _text(payload: Any) -> str:
    try:
        candidate = payload["candidates"][0]
        parts = candidate["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        reason = payload.get("promptFeedback") if isinstance(payload, dict) else None
        raise ModelWriterError(f"LLM returned no candidate ({reason or 'empty'})") from exc
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text.strip():
        raise ModelWriterError(f"LLM returned no text (finish: {candidate.get('finishReason')})")
    return text
