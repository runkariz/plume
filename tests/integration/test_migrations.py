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
    assert result.after == "0008"

    # Idempotent.
    assert not MigrateSchema(migrator).execute().changed

    migrator.downgrade_to_base()
    assert migrator.current_revision() is None
    migrator.upgrade_to_head()
    assert migrator.current_revision() == "0008"


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
    command.upgrade(cfg, "0008")
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
