"""``SchemaMigrator`` backed by Alembic. The migration scripts ship inside the package."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # ConfigParser interpolation: a literal '%' in the URL (encoded password) must be doubled.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


class AlembicMigrator:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _config(self) -> Config:
        return alembic_config(self._engine.url.render_as_string(hide_password=False))

    def current_revision(self) -> str | None:
        with self._engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()

    def upgrade_to_head(self) -> None:
        command.upgrade(self._config(), "head")

    def downgrade_to_base(self) -> None:
        command.downgrade(self._config(), "base")
