"""Level 1, step 1 against `docker compose up` (Postgres on 127.0.0.1:18432), hash embedder.

Started by `make e2e`. Uses the installed `plume` CLI as a user would.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.e2e
PLUME = str(Path(sys.executable).parent / "plume")
PACKAGES = Path(__file__).resolve().parents[1] / "fixtures" / "packages"


def _plume(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PLUME_EMBEDDER": "hash"}
    return subprocess.run([PLUME, *args], capture_output=True, text=True, check=False, env=env)


def _load(path: Path) -> dict[str, object]:
    result = _plume("load", str(path), "--json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


@pytest.fixture(scope="module", autouse=True)
def _fresh_schema() -> None:
    engine = make_engine(Settings().sqlalchemy_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    assert _plume("migrate").returncode == 0


def test_compose_postgres_has_pgvector() -> None:
    engine = make_engine(Settings().sqlalchemy_url)
    try:
        with engine.begin() as conn:
            ext = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
        assert ext
    finally:
        engine.dispose()


def test_migrate_is_idempotent() -> None:
    result = _plume("migrate")
    assert result.returncode == 0
    assert "up to date: 0013" in result.stdout


def test_ingest_two_apis_stable_ids_and_diff(tmp_path: Path) -> None:
    a = _load(PACKAGES / "test-catalog")
    b = _load(PACKAGES / "second-catalog")
    assert (a["api"], b["api"]) == ("test-catalog-api", "second-catalog-api")
    assert a["tag"] == b["tag"] == "latest"

    again = _load(PACKAGES / "test-catalog")
    assert again["build"] == a["build"]
    assert again["reused"] is True

    copy = tmp_path / "catalog-v2"
    shutil.copytree(PACKAGES / "test-catalog", copy)
    order = copy / "connector" / "models" / "order.schema.json"
    data = json.loads(order.read_text())
    data["properties"]["status"] = {"type": "string", "description": "Order status."}
    order.write_text(json.dumps(data))
    (copy / "connector" / "models" / "error.schema.json").unlink()
    v2 = _load(copy)
    assert v2["previous"] == a["build"]

    diff = _plume("diff", str(a["build"]), str(v2["build"]))
    assert diff.returncode == 0
    changes = json.loads(diff.stdout)
    assert changes["changed"] == ["model:order#0"]
    assert changes["removed"] == ["model:error#0"]
    assert changes["added"] == []

    apis = _plume("apis").stdout
    assert "test-catalog-api" in apis
    assert "second-catalog-api" in apis
