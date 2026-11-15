"""Use case: migrate the database schema to the latest revision."""

from dataclasses import dataclass

from plume.application.ports.schema_migrator import SchemaMigrator


@dataclass(frozen=True, slots=True)
class MigrationResult:
    before: str | None
    after: str | None

    @property
    def changed(self) -> bool:
        return self.before != self.after


class MigrateSchema:
    def __init__(self, migrator: SchemaMigrator) -> None:
        self._migrator = migrator

    def execute(self) -> MigrationResult:
        before = self._migrator.current_revision()
        self._migrator.upgrade_to_head()
        return MigrationResult(before=before, after=self._migrator.current_revision())
