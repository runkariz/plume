"""Removing an API on Postgres: every table that holds its data, one transaction, an audit row;
the other APIs are untouched."""

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from plume.bootstrap.container import Container
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration
GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "gold"
API = "test-catalog-api"


def test_remove_api_on_postgres(
    clean_engine: Engine, pg_url: str, packages: Path, tmp_path: Path
) -> None:
    c = Container(
        settings=Settings(database_url=pg_url, embedder="hash", data_dir=tmp_path,
                          gold_dirs=(GOLD,))
    )  # fmt: skip
    c.build_pipeline().execute("job", str(packages / "test-catalog"))
    copy = tmp_path / "v2"
    shutil.copytree(packages / "test-catalog", copy)
    path = copy / "connector" / "models" / "order.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"].pop("currency")
    path.write_text(json.dumps(schema))
    c.build_pipeline().execute("job", str(copy))  # a second build, with release notes
    c.build_pipeline().execute("job", str(packages / "shopify-mini"))
    c.api_display().set(API, "Catalog")

    def count(sql: str) -> int:
        with c.engine.connect() as conn:
            return int(conn.execute(text(sql), {"a": API}).scalar_one())

    builds = "SELECT build_id FROM builds WHERE api_id = :a"
    before = {
        "documents": count(f"SELECT count(*) FROM documents WHERE build_id IN ({builds})"),  # noqa: S608
        "notes": count("SELECT count(*) FROM release_notes WHERE api_id = :a"),
        "shopify": count(
            "SELECT count(*) FROM documents d JOIN builds b USING (build_id) "
            "WHERE b.api_id = 'shopify'"
        ),
    }
    assert before["documents"] > 0
    assert before["notes"] == 1
    out = c.remove_api().execute(API, API, reason="integration test")
    assert out["removed"]["builds"] == 2
    assert out["removed"]["documents"] == before["documents"]
    assert out["removed"]["releaseNotes"] == 1
    assert out["removed"]["displayName"] == 1
    for table in ("apis", "builds", "tags", "evals", "release_notes", "api_display_names"):
        assert count(f"SELECT count(*) FROM {table} WHERE api_id = :a") == 0, table  # noqa: S608
    assert count("SELECT count(*) FROM documents WHERE build_id LIKE 'b-%' AND build_id "
                 "NOT IN (SELECT build_id FROM builds)") == 0  # fmt: skip
    assert count("SELECT count(*) FROM documents d JOIN builds b USING (build_id) "
                 "WHERE b.api_id = 'shopify'") == before["shopify"]  # fmt: skip
    with c.engine.connect() as conn:
        audit = conn.execute(text("SELECT api_id, forced, reason, counts FROM api_removals")).one()
    assert (audit.api_id, audit.forced, audit.reason) == (API, False, "integration test")
    assert audit.counts["builds"] == 2
    assert c.resolver().resolve("shopify").build is not None
    c.engine.dispose()
