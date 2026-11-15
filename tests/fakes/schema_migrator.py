"""In-memory ``SchemaMigrator``."""


class FakeSchemaMigrator:
    def __init__(self, revisions: list[str], current: str | None = None) -> None:
        self._revisions = revisions
        self.current = current
        self.upgrades = 0

    def current_revision(self) -> str | None:
        return self.current

    def upgrade_to_head(self) -> None:
        self.upgrades += 1
        self.current = self._revisions[-1] if self._revisions else None
