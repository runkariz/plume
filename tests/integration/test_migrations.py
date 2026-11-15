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
    assert result.after == "0005"

    # Idempotent.
    assert not MigrateSchema(migrator).execute().changed

    migrator.downgrade_to_base()
    assert migrator.current_revision() is None
    migrator.upgrade_to_head()
    assert migrator.current_revision() == "0005"


def test_pgvector_is_available(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        distance = conn.execute(text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector")).scalar_one()
    assert distance == pytest.approx(1.0)
