"""Port: bring the database schema to the latest revision."""

from typing import Protocol


class SchemaMigrator(Protocol):
    def current_revision(self) -> str | None:
        """The applied revision, or ``None`` on an empty database."""
        ...

    def upgrade_to_head(self) -> None: ...
