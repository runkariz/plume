import pytest
from sqlalchemy import Engine, text

from plume.application.system.migrate_schema import MigrateSchema
from plume.infrastructure.db.alembic_migrator import AlembicMigrator

pytestmark = pytest.mark.integration


def test_migration_from_empty_to_head_and_back(engine: Engine) -> None:
    migrator = AlembicMigrator(engine)
    migrator.downgrade_to_base()
    assert migrator.current_revision() is None

    result = MigrateSchema(migrator).execute()
    assert result.before is None
    assert result.after == "0015"

    # Idempotent.
    assert not MigrateSchema(migrator).execute().changed

    migrator.downgrade_to_base()
    assert migrator.current_revision() is None
    migrator.upgrade_to_head()
    assert migrator.current_revision() == "0015"


def test_pgvector_is_available(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        distance = conn.execute(text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector")).scalar_one()
    assert distance == pytest.approx(1.0)


def test_0007_keeps_existing_models_official(engine: Engine) -> None:
    from alembic import command  # noqa: PLC0415

    migrator = AlembicMigrator(engine)
    migrator.downgrade_to_base()
    cfg = migrator._config()
    command.upgrade(cfg, "0006")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO model_sessions (session_id, concept, inputs, created_at) "
                "VALUES ('s-old', 'Order', '[]', now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO model_snapshots (snapshot_id, session_id, concept, apis, inputs, "
                "model, citations_checked, prompt_version, created_at) VALUES ('m-old', 's-old', "
                "'Order', '{a,b}', '[]', '{}', 1, 'v1', now())"
            )
        )
    command.upgrade(cfg, "0007")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT visibility, origin, lineage_id, version, content_key, released_at "
                "FROM model_snapshots WHERE snapshot_id = 'm-old'"
            )
        ).one()
        lineage = conn.execute(
            text("SELECT owner_key_hash FROM model_lineages WHERE lineage_id = 'm-old'")
        ).one()
    assert (row.visibility, row.origin, row.lineage_id, row.version, row.content_key) == (
        "official",
        "maintainer",
        "m-old",
        1,
        "m-old",
    )
    assert row.released_at is not None
    assert lineage.owner_key_hash is None
    migrator.downgrade_to_base()
    migrator.upgrade_to_head()


def test_0012_turns_owner_keys_into_collections(engine: Engine) -> None:
    """Every owner-key hash becomes one collection holding its model and set lineages; the
    old key still finds it."""
    from alembic import command  # noqa: PLC0415

    from plume.application.models.collections import owner_key_hash  # noqa: PLC0415
    from plume.infrastructure.db.repos.collection_repo import (  # noqa: PLC0415
        PostgresCollectionRepo,
    )

    migrator = AlembicMigrator(engine)
    migrator.downgrade_to_base()
    cfg = migrator._config()
    command.upgrade(cfg, "0011")
    h = owner_key_hash("pk_old")
    with engine.begin() as conn:
        for table, lineage in (("model_lineages", "u-1"), ("model_lineages", "u-2"),
                               ("model_set_lineages", "us-1")):  # fmt: skip
            conn.execute(
                text(
                    f"INSERT INTO {table} (lineage_id, owner_key_hash, created_at) "  # noqa: S608
                    "VALUES (:l, :h, now())"
                ),
                {"l": lineage, "h": h},
            )
        conn.execute(
            text(
                "INSERT INTO model_lineages (lineage_id, owner_key_hash, created_at) "
                "VALUES ('m-official', NULL, now())"
            )
        )
    command.upgrade(cfg, "0012")
    command.upgrade(cfg, "head")  # the repo reads today's columns (0013: version_id)
    repo = PostgresCollectionRepo(engine)
    found = repo.for_legacy_keys([h])
    assert len(found) == 1
    assert found[0].startswith("c-")
    assert sorted(repo.items(found[0])) == [
        ("model", "u-1", None), ("model", "u-2", None), ("set", "us-1", None),
    ]  # fmt: skip
    assert repo.containing("model", "m-official") == []
    migrator.downgrade_to_base()
    migrator.upgrade_to_head()
