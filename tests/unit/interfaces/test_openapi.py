"""docs/openapi.json is the published contract for the web client: keep it current."""

import json
from pathlib import Path

from plume.bootstrap.container import Container
from plume.bootstrap.servers import openapi_document
from plume.infrastructure.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


def test_committed_openapi_matches_the_app() -> None:
    generated = openapi_document(Container(settings=Settings(embedder="hash")))
    committed = (ROOT / "docs" / "openapi.json").read_text(encoding="utf-8")
    assert json.loads(committed) == json.loads(generated), (
        "docs/openapi.json is stale: run `uv run plume openapi --out docs/openapi.json`"
    )


def test_openapi_has_the_reader_routes() -> None:
    spec = json.loads(openapi_document(Container(settings=Settings(embedder="hash"))))
    paths = set(spec["paths"])
    assert {
        "/v1/apis",
        "/v1/apis/{api}",
        "/v1/apis/{api}/items",
        "/v1/apis/{api}/search",
        "/v1/apis/{api}/ask",
        "/v1/apis/{api}/check-call",
        "/v1/apis/{api}/find-fact",
        "/v1/apis/{api}/documents/{doc_id}",
        "/v1/apis/{api}/builds",
        "/v1/apis/{api}/diff",
    } <= paths
    assert "recallAt5" in spec["components"]["schemas"]["ApiStatus"]["properties"]
