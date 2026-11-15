"""The Vertex Gemini writer: key from a file per call, only in a header, never in errors."""

import json
from pathlib import Path

import httpx
import pytest

from plume.application.ports.model_writer import (
    ModelWriterError,
    ModelWriterUnavailableError,
    Turn,
)
from plume.infrastructure.llm.vertex_gemini import VertexGeminiWriter

SECRET = "vx-test-secret-0123456789"


def _writer(tmp_path: Path, handler: httpx.MockTransport) -> VertexGeminiWriter:
    key = tmp_path / "key"
    key.write_text(SECRET + "\n")
    return VertexGeminiWriter(
        key, "gemini-x", client=httpx.Client(transport=handler), sleep=lambda _: None
    )


def test_request_shape_and_reply(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        reply = {"candidates": [{"content": {"parts": [{"text": '{"name": "Order"}'}]}}]}
        return httpx.Response(200, json=reply)

    writer = _writer(tmp_path, httpx.MockTransport(handle))
    assert writer.available()
    assert writer.name == "gemini:gemini-x"
    assert writer.write("sys", [Turn("user", "hi")]) == '{"name": "Order"}'
    request = seen[0]
    assert request.headers["x-goog-api-key"] == SECRET
    assert SECRET not in str(request.url)
    assert str(request.url).endswith("/models/gemini-x:generateContent")
    body = json.loads(request.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_retries_then_errors_without_the_key(tmp_path: Path) -> None:
    calls = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429 if calls < 3 else 500, text=f"echo {SECRET}")

    writer = _writer(tmp_path, httpx.MockTransport(handle))
    with pytest.raises(ModelWriterError) as exc:
        writer.write("s", [Turn("user", "x")])
    assert SECRET not in str(exc.value)
    assert calls == 5  # 1 + 4 retries
    forbidden = _writer(tmp_path, httpx.MockTransport(lambda _: httpx.Response(403)))
    with pytest.raises(ModelWriterUnavailableError):
        forbidden.write("s", [Turn("user", "x")])


def test_no_key_file_is_unavailable(tmp_path: Path) -> None:
    writer = VertexGeminiWriter(tmp_path / "missing")
    assert not writer.available()
    with pytest.raises(ModelWriterUnavailableError):
        writer.write("s", [])
    assert not VertexGeminiWriter(None).available()
