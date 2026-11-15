"""Wires ports to adapters from the settings. Tests build their own container with fakes."""

from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import Engine

from plume.application.system.migrate_schema import MigrateSchema
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings = field(default_factory=get_settings)

    @cached_property
    def engine(self) -> Engine:
        return make_engine(self.settings.sqlalchemy_url)

    def migrate_schema(self) -> MigrateSchema:
        return MigrateSchema(AlembicMigrator(self.engine))
