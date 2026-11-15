"""Level 1 against compose: the maintainer wizard over HTTP (upload -> review -> build with SSE
-> publish), and export -> restore into an EMPTY database with golden reader answers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from plume.bootstrap.container import Container
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.settings import Settings
from tests.unit.infrastructure.test_dumps_and_storage import zip_dir

pytestmark = pytest.mark.e2e
API = "http://127.0.0.1:18480"
PLUME = str(Path(sys.executable).parent / "plume")
PACKAGES = Path(__file__).resolve().parents[1] / "fixtures" / "packages"


@pytest.fixture
def auth() -> dict[str, str]:
    token = os.environ.get("PLUME_E2E_TOKEN")
    if not token:
        pytest.skip("PLUME_E2E_TOKEN not set (run through `make e2e`)")
    return {"Authorization": f"Bearer {token}"}


def test_wizard_over_http_with_sse(auth: dict[str, str]) -> None:
    with httpx.Client(base_url=API, timeout=30) as http:
        assert http.get("/v1/maintainer/me").status_code == 401
        assert http.get("/v1/maintainer/me", headers=auth).json() == {"name": "maintainer"}
        data = zip_dir(PACKAGES / "second-catalog", "second/")
        r = http.post("/v1/packages", headers=auth, files={"file": ("second.zip", data)})
        assert r.status_code == 201, r.text
        jid = r.json()["id"]
        r = http.post(
            f"/v1/jobs/{jid}/review",
            headers=auth,
            json={"apiId": "second-catalog-api", "displayName": "Second", "tag": "latest"},
        )
        assert r.json()["status"] == "reviewed"
        assert http.post(f"/v1/jobs/{jid}/build", headers=auth).status_code == 200

        events = []
        with http.stream("GET", f"/v1/jobs/{jid}/events", headers=auth) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        assert events[-1]["type"] == "done"
        assert events[-1]["status"] == "staged", events[-1]
        assert {e["type"] for e in events} >= {"service", "step", "log", "done"}

        job = http.get(f"/v1/jobs/{jid}", headers=auth).json()
        assert job["eval"]["gate"]["passed"] is True
        assert http.post(f"/v1/jobs/{jid}/publish", headers=auth).json()["status"] == "published"
        dump = http.get(f"/v1/jobs/{jid}/dump", headers=auth)
        assert dump.content[:2] == b"\x1f\x8b"


def test_export_restore_into_empty_database(tmp_path: Path) -> None:
    env = {**os.environ, "PLUME_EMBEDDER": "hash", "PLUME_DATA_DIR": str(tmp_path)}
    load = subprocess.run(
        [PLUME, "load", str(PACKAGES / "shopify-mini"), "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert load.returncode == 0, load.stderr
    out = tmp_path / "shopify.plume.jsonl.gz"
    exp = subprocess.run(
        [PLUME, "export", "shopify", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert exp.returncode == 0, exp.stderr

    source_url = Settings().sqlalchemy_url
    admin = make_engine(source_url).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS plume_restore WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE plume_restore"))
    target_url = (
        make_url(source_url).set(database="plume_restore").render_as_string(hide_password=False)
    )
    try:
        renv = {**env, "PLUME_DATABASE_URL": target_url}
        assert subprocess.run([PLUME, "migrate"], env=renv, check=False).returncode == 0
        res = subprocess.run(
            [PLUME, "restore", str(out), "--tag", "latest"],
            capture_output=True,
            text=True,
            check=False,
            env=renv,
        )
        assert res.returncode == 0, res.stderr
        assert "restored" in res.stdout

        src = Container(settings=Settings(embedder="hash"))
        dst = Container(settings=Settings(database_url=target_url, embedder="hash"))
        AlembicMigrator(dst.engine).upgrade_to_head()
        for query in ("assigned fulfillment orders", "list products", "rate limits"):
            a = src.search().execute("shopify", query)
            b = dst.search().execute("shopify", query)
            assert [h.doc_id for h in a.hits] == [h.doc_id for h in b.hits]
            assert a.ref.build == b.ref.build
        fa = src.find_fact().execute("shopify", "since_id")
        fb = dst.find_fact().execute("shopify", "since_id")
        assert fa.matches == fb.matches
        src.engine.dispose()
        dst.engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS plume_restore WITH (FORCE)"))
        admin.dispose()
