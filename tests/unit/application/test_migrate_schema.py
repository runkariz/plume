from plume.application.system.migrate_schema import MigrateSchema
from tests.fakes.schema_migrator import FakeSchemaMigrator


def test_migrates_an_empty_database() -> None:
    fake = FakeSchemaMigrator(["0001"])
    result = MigrateSchema(fake).execute()
    assert (result.before, result.after, result.changed) == (None, "0001", True)


def test_up_to_date_database_reports_no_change() -> None:
    fake = FakeSchemaMigrator(["0001"], current="0001")
    result = MigrateSchema(fake).execute()
    assert not result.changed
    assert fake.upgrades == 1
