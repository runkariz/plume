"""The real stack (Postgres adapters, package reader, hash embedder) through the CLI."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from plume.bootstrap.cli import build_app
from plume.bootstrap.container import Container
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration
runner = CliRunner()


@pytest.fixture
def app(clean_engine: Engine, pg_url: str) -> Iterator[typer.Typer]:
    container = Container(settings=Settings(database_url=pg_url, embedder="hash"))
    yield build_app(container)
    container.engine.dispose()


def _load(app: typer.Typer, path: Path, *extra: str) -> dict[str, object]:
    result = runner.invoke(app, ["load", str(path), "--json", *extra])
    assert result.exit_code == 0, result.output
    return json.loads(result.output.strip().splitlines()[-1])  # type: ignore[no-any-return]


def test_load_two_apis_reload_and_diff(
    app: typer.Typer, packages: Path, tmp_path: Path, clean_engine: Engine
) -> None:
    a = _load(app, packages / "test-catalog")
    b = _load(app, packages / "second-catalog")
    assert a["api"] == "test-catalog-api"
    assert b["api"] == "second-catalog-api"
    assert a["embedded"] == a["chunks"]
    # The two catalogs share text (same models), so the second reuses cached vectors.
    assert b["from_cache"] > 0  # type: ignore[operator]

    again = _load(app, packages / "test-catalog")
    assert again["build"] == a["build"]
    assert again["reused"] is True

    copy = tmp_path / "v2"
    shutil.copytree(packages / "test-catalog", copy)
    (copy / "connector" / "models" / "error.schema.json").unlink()
    v2 = _load(app, copy)
    assert v2["previous"] == a["build"]
    diff = json.loads(runner.invoke(app, ["diff", str(a["build"]), str(v2["build"])]).output)
    assert diff["removed"] == ["model:error#0"]
    assert diff["added"] == []
    assert diff["changed"] == []

    with clean_engine.connect() as conn:
        missing = conn.execute(text("SELECT count(*) FROM chunks WHERE embedding IS NULL")).scalar()
        sealed = conn.execute(text("SELECT count(*) FROM builds WHERE status = 'sealed'")).scalar()
        facts = conn.execute(
            text("SELECT count(*) FROM facts WHERE build_id = :b"), {"b": a["build"]}
        ).scalar()
    assert missing == 0
    assert sealed == 3
    assert facts == a["facts"]

    out = runner.invoke(app, ["builds", "test-catalog-api"]).output.splitlines()
    assert out[0].startswith(str(v2["build"]))
    assert out[0].endswith("latest")
    rollback = runner.invoke(app, ["tag", str(a["build"]), "latest"])
    assert f"{v2['build']} -> {a['build']}" in rollback.output


def test_shopify_mini_full_text_and_facts(
    app: typer.Typer, packages: Path, clean_engine: Engine
) -> None:
    s = _load(app, packages / "shopify-mini")
    with clean_engine.connect() as conn:
        top = conn.execute(
            text(
                "SELECT doc_id FROM chunks WHERE build_id = :b "
                "ORDER BY ts_rank(tsv, websearch_to_tsquery('english', :q)) DESC LIMIT 1"
            ),
            {"b": s["build"], "q": "assigned fulfillment orders"},
        ).scalar()
        scope = conn.execute(
            text(
                "SELECT owner_id FROM facts WHERE build_id = :b AND kind = 'scope' AND name = :n "
                "AND owner_kind = 'endpoint'"
            ),
            {"b": s["build"], "n": "read_assigned_fulfillment_orders"},
        ).scalar()
    assert top is not None
    assert "assigned_fulfillment_orders" in top
    assert scope == top
