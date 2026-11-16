"""Level 1 step 4 on Postgres: export -> restore into an EMPTY database -> same answers."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from plume.bootstrap.container import Container
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration
GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "gold"


@pytest.fixture
def second_url(pg_url: str, migrated_engine: Engine) -> Iterator[str]:
    admin = migrated_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS plume_restore"))
        conn.execute(text("CREATE DATABASE plume_restore"))
    url = make_url(pg_url).set(database="plume_restore").render_as_string(hide_password=False)
    yield url
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS plume_restore WITH (FORCE)"))


def _container(url: str, tmp: Path) -> Container:
    return Container(
        settings=Settings(database_url=url, embedder="hash", data_dir=tmp, gold_dirs=(GOLD,))
    )


def _answers(c: Container) -> dict[str, object]:
    search = c.search().execute("shopify", "assigned fulfillment orders")
    fact = c.find_fact().execute("shopify", "since_id")
    absent = c.find_fact().execute("test-catalog-api", "loyalty_points")
    call = c.check_call().execute(
        "shopify", "GET", "/admin/api/2026-10/products/1.json", ["fields"]
    )
    return {
        "search": [(h.doc_id, h.dense_rank, h.text_rank) for h in search.hits],
        "fact": [(m.owner_id, m.location, m.citation) for m in fact.matches],
        "absent": (absent.found, absent.complete, absent.checked),
        "call": (call.verdict, call.matched_path, call.params),
        "builds": (search.ref.build, fact.ref.build),
    }


def test_restore_into_empty_database_gives_the_same_answers(
    clean_engine: Engine, pg_url: str, second_url: str, packages: Path, tmp_path: Path
) -> None:
    src = _container(pg_url, tmp_path)
    for name in ("shopify-mini", "test-catalog"):
        result = src.build_pipeline().execute("job", str(packages / name))
        assert result.gate is not None
        assert result.gate.passed
    shop = src.resolver().resolve("shopify").build.build_id
    cat = src.resolver().resolve("test-catalog-api").build.build_id
    dumps = [src.export_dump().execute(b) for b in (shop, cat)]
    expected = _answers(src)

    dst = _container(second_url, tmp_path)
    AlembicMigrator(dst.engine).upgrade_to_head()
    for ref in dumps:
        r = dst.restore_dump().execute(ref, ["latest"])
        assert r.restored
    assert _answers(dst) == expected
    assert dst.evals.get(shop) == src.evals.get(shop)
    # A restored build is sealed and identical: exporting it again gives the same bytes.
    assert dst.export_dump().bytes(shop) == src.export_dump().bytes(shop)
    assert dst.restore_dump().execute(dumps[0]).restored is False
    src.engine.dispose()
    dst.engine.dispose()


def test_release_notes_are_computed_on_postgres_and_travel_with_the_dump(
    clean_engine: Engine, pg_url: str, second_url: str, packages: Path, tmp_path: Path
) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    src = _container(pg_url, tmp_path)
    first = src.build_pipeline().execute("job", str(packages / "test-catalog")).build_id
    copy = tmp_path / "catalog-v2"
    shutil.copytree(packages / "test-catalog", copy)
    path = copy / "connector" / "models" / "order.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"].pop("currency")
    path.write_text(json.dumps(schema))
    second = src.build_pipeline().execute("job", str(copy))
    assert second.notes is not None
    assert second.notes["from"] == first.value
    notes = src.release_notes().get("test-catalog-api", second.build_id.value)
    assert any(i["subject"]["fieldPath"] == "currency" and i["op"] == "removed"
               for i in notes["items"])  # fmt: skip
    rolled = src.release_notes().rollback("test-catalog-api", second.build_id.value, "test")
    assert rolled["buildId"] == first.value
    ref = src.export_dump().execute(second.build_id)

    dst = _container(second_url, tmp_path)
    AlembicMigrator(dst.engine).upgrade_to_head()
    dst.restore_dump().execute(ref)
    restored = dst.release_notes_repo.get(second.build_id.value)
    assert restored == src.release_notes_repo.get(second.build_id.value)
    assert restored is not None
    assert restored["review"] == "rolled_back"
    assert dst.release_notes_repo.get_meta(second.build_id.value) == (
        src.release_notes_repo.get_meta(second.build_id.value)
    )
    src.engine.dispose()
    dst.engine.dispose()
