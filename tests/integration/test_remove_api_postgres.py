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


def _official_set_on_postgres(c: Container, packages: Path) -> tuple[str, list[str]]:
    """A released (official) set with official members, built on the fake stack with the set
    tests' helpers, then stored in Postgres (sessions first: foreign keys)."""
    from tests.fakes.knowledge import WordEmbedder  # noqa: PLC0415
    from tests.fakes.stack import FakeStack  # noqa: PLC0415
    from tests.unit.application.test_model_sets import _relation, _set, _setup  # noqa: PLC0415

    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    sets = s.model_sets()
    session, pins, ids = _setup(s, maintainer=True)
    draft = sets.submit(session.session_id, _set(ids, _relation(s, pins)), maintainer=True)
    released = sets.release(draft.snapshot.set_id).snapshot
    for ms in s.models_repo.sessions.values():
        c.models_repo.save_session(ms)
    for snap in s.models_repo.snapshots.values():
        c.models_repo.save_snapshot(snap)
    for ss in s.sets_repo.sessions.values():
        c.model_sets_repo.save_session(ss)
    c.model_sets_repo.save_set(s.sets_repo.sets[released.set_id])
    return released.set_id, list(ids.values())


def test_forced_removal_retires_an_official_set_atomically(
    clean_engine: Engine,
    pg_url: str,
    packages: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plume.infrastructure.db.repos import api_removal  # noqa: PLC0415

    c = Container(
        settings=Settings(database_url=pg_url, embedder="hash", data_dir=tmp_path,
                          gold_dirs=(GOLD,))
    )  # fmt: skip
    for p in ("test-catalog", "second-catalog"):
        c.build_pipeline().execute("job", str(packages / p))
    set_id, models = _official_set_on_postgres(c, packages)
    pinned = {p["id"] for p in c.remove_api().pinned_by("second-catalog-api")}
    assert {set_id, *models} <= pinned
    # a failure after the retire step rolls EVERYTHING back (models and set untouched)
    monkeypatch.setattr(api_removal, "_STEPS", (*api_removal._STEPS, ("boom", "SELECT 1/0")))
    with pytest.raises(Exception, match="division by zero"):
        c.remove_api().execute("second-catalog-api", "second-catalog-api", force=True)
    assert c.model_sets_repo.get_set(set_id).visibility == "official"  # type: ignore[union-attr]
    assert all(c.models_repo.get_snapshot(m).visibility == "official" for m in models)  # type: ignore[union-attr]
    monkeypatch.undo()
    out = c.remove_api().execute("second-catalog-api", "second-catalog-api", force=True)
    now = {r["id"]: r["now"] for r in out["retired"]}
    assert now[set_id] == "discarded"  # a set has no "superseded" state
    assert all(now[m] == "superseded" for m in models)
    assert c.model_sets_repo.get_set(set_id).visibility == "discarded"  # type: ignore[union-attr]
    assert c.apis.get(__import__("plume.domain.knowledge.api", fromlist=["ApiId"]).ApiId(
        "second-catalog-api")) is None  # fmt: skip
    c.engine.dispose()
