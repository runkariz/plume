"""Vertex through Application Default Credentials (Workload Identity): a fake credentials
provider; no live ADC here."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from plume.application.errors import EmbeddingError
from plume.application.ports.model_writer import ModelWriterUnavailableError, Turn
from plume.infrastructure.embeddings.gemini import GeminiEmbedder
from plume.infrastructure.llm.vertex_gemini import VertexGeminiWriter
from plume.infrastructure.settings import Settings
from plume.infrastructure.vertex_auth import AdcTokenSource, VertexAuthError, auth_headers

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


class FakeCreds:
    def __init__(self, clock: list[float] | None = None) -> None:
        self.token: str | None = None
        self.expiry: datetime | None = None
        self.refreshes = 0
        self._clock = clock

    def refresh(self) -> None:
        self.refreshes += 1
        self.token = f"tok-{self.refreshes}"
        now = datetime.fromtimestamp(self._clock[0], UTC) if self._clock else NOW
        self.expiry = now + timedelta(hours=1)


def _source(creds: FakeCreds, now: list[float]) -> AdcTokenSource:
    return AdcTokenSource(
        loader=lambda: (creds, "proj"), refresh=lambda c: c.refresh(), now=lambda: now[0]
    )


def test_tokens_are_refreshed_only_when_missing_or_close_to_expiry() -> None:
    clock = [NOW.timestamp()]
    creds = FakeCreds(clock)
    source = _source(creds, clock)
    assert source.available()
    assert source.token() == "tok-1"
    assert source.token() == "tok-1"  # still fresh
    clock[0] += 3600 - 200  # within the 5-minute margin
    assert source.token() == "tok-2"
    assert creds.refreshes == 2
    assert auth_headers(None, source) == {"Authorization": "Bearer tok-2"}
    assert auth_headers("k", source) == {"x-goog-api-key": "k"}  # a key wins


def test_missing_credentials_are_reported_without_detail() -> None:
    def no_adc() -> tuple[Any, str | None]:
        raise RuntimeError("secret path /home/x/.config/gcloud leaked?")

    source = AdcTokenSource(loader=no_adc)
    assert not source.available()
    with pytest.raises(VertexAuthError) as exc:
        source.token()
    assert "RuntimeError" in str(exc.value)
    assert "gcloud" not in str(exc.value)


def test_embedder_uses_the_bearer_token_on_the_project_url() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"predictions": [{"embeddings": {"values": [3.0, 4.0]}}]})

    embedder = GeminiEmbedder(
        api_key="",
        dims=2,
        client=httpx.Client(transport=httpx.MockTransport(handle)),
        token_source=_source(FakeCreds(), [NOW.timestamp()]),
        project="proj",
        location="us-central1",
    )
    assert embedder.embed_query("hi") == (0.6, 0.8)
    request = seen[0]
    assert str(request.url) == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/proj/locations/us-central1/"
        "publishers/google/models/gemini-embedding-001:predict"
    )
    assert request.headers["authorization"] == "Bearer tok-1"
    assert "x-goog-api-key" not in request.headers
    with pytest.raises(EmbeddingError, match="PLUME_VERTEX_PROJECT"):
        GeminiEmbedder(api_key="", token_source=_source(FakeCreds(), [0.0]))


def test_writer_uses_adc_without_a_key_file_and_a_key_file_otherwise(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    tokens = _source(FakeCreds(), [NOW.timestamp()])
    adc = VertexGeminiWriter(None, "gemini-x", client=client, project="proj", token_source=tokens)
    assert adc.available()
    assert adc.write("sys", [Turn("user", "hi")]) == "{}"
    assert seen[-1].headers["authorization"] == "Bearer tok-1"
    assert "/projects/proj/locations/global/" in str(seen[-1].url)
    # no project: ADC cannot be used (express URLs take keys only)
    assert not VertexGeminiWriter(None, "gemini-x", token_source=tokens).available()
    key = tmp_path / "key"
    key.write_text("k-secret")
    keyed = VertexGeminiWriter(key, "gemini-x", client=client, project="proj", token_source=tokens)
    keyed.write("sys", [Turn("user", "hi")])
    assert seen[-1].headers["x-goog-api-key"] == "k-secret"
    assert "authorization" not in seen[-1].headers

    def no_adc() -> tuple[Any, str | None]:
        raise RuntimeError

    broken = VertexGeminiWriter(
        None, "gemini-x", client=client, project="proj", token_source=AdcTokenSource(no_adc)
    )
    assert not broken.available()
    with pytest.raises(ModelWriterUnavailableError, match="Application Default Credentials"):
        broken.write("sys", [Turn("user", "hi")])


@pytest.mark.parametrize(
    ("env", "adc"),
    [
        ({}, False),
        ({"vertex_project": "p"}, True),  # no key + a project: ADC
        ({"vertex_project": "p", "vertex_api_key": "k"}, False),  # a key wins
        ({"vertex_project": "p", "vertex_auth": "key"}, False),
        ({"vertex_auth": "adc", "vertex_project": "p", "vertex_api_key": "k"}, True),
    ],
)
def test_settings_choose_adc(env: dict[str, Any], adc: bool) -> None:
    assert Settings(**env).vertex_uses_adc() is adc


@pytest.mark.parametrize(
    ("project", "location", "url"),
    [
        (None, "europe-west3",  # no project: the express URL, location ignored
         "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-embedding-001:predict"),
        ("proj", "europe-west3",
         "https://europe-west3-aiplatform.googleapis.com/v1/projects/proj/locations/europe-west3/"
         "publishers/google/models/gemini-embedding-001:predict"),
        ("proj", "global",
         "https://aiplatform.googleapis.com/v1/projects/proj/locations/global/"
         "publishers/google/models/gemini-embedding-001:predict"),
    ],
)  # fmt: skip
def test_a_key_with_a_project_pins_the_embedding_location(
    project: str | None, location: str, url: str
) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"predictions": [{"embeddings": {"values": [1.0, 0.0]}}]})

    embedder = GeminiEmbedder(
        api_key="k-secret",
        dims=2,
        client=httpx.Client(transport=httpx.MockTransport(handle)),
        project=project,
        location=location,
    )
    embedder.embed_query("hi")
    assert str(seen[0].url) == url
    assert seen[0].headers["x-goog-api-key"] == "k-secret"
    assert "authorization" not in seen[0].headers


def test_the_container_passes_project_and_embed_location_in_key_mode() -> None:
    from plume.bootstrap.container import Container  # noqa: PLC0415

    settings = Settings(
        embedder="vertex",
        vertex_api_key="k-secret",
        vertex_project="proj",
        vertex_embed_location="europe-west4",
    )
    c = Container(settings=settings)
    url = c.embedder._vertex_url()  # type: ignore[attr-defined]
    assert url.startswith("https://europe-west4-aiplatform.googleapis.com/v1/projects/proj/")


def test_gemini_embedding_2_uses_batch_embed_contents_on_the_rep_host() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        n = len(json.loads(request.content)["requests"])
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0]}] * n})

    embedder = GeminiEmbedder(
        api_key="k-ignored",  # -2 does not take API keys: the ADC token is used
        model="gemini-embedding-2",
        dims=2,
        batch_size=1000,  # capped at the API's 250
        client=httpx.Client(transport=httpx.MockTransport(handle)),
        token_source=_source(FakeCreds(), [NOW.timestamp()]),
        project="proj",
        location="eu",
    )
    out = embedder.embed_documents([f"t{i}" for i in range(300)])
    assert len(out) == 300
    assert out[0] == (0.6, 0.8)
    assert [len(json.loads(r.content)["requests"]) for r in seen] == [250, 50]
    assert str(seen[0].url) == (
        "https://aiplatform.eu.rep.googleapis.com/v1/projects/proj/locations/eu/publishers/"
        "google/models/gemini-embedding-2:batchEmbedContents"
    )
    body = json.loads(seen[0].content)["requests"][0]
    assert body == {"content": {"parts": [{"text": "t0"}]}, "outputDimensionality": 2}
    assert seen[0].headers["authorization"] == "Bearer tok-1"
    assert "x-goog-api-key" not in seen[0].headers


def test_gemini_embedding_2_needs_adc_and_a_project() -> None:
    with pytest.raises(EmbeddingError, match="does not accept API keys"):
        GeminiEmbedder(api_key="k", model="gemini-embedding-2", project="proj")
