from typer.testing import CliRunner

from plume import __version__
from plume.application.system.migrate_schema import MigrateSchema
from plume.interfaces.cli.main import CliDependencies, create_app
from tests.fakes.schema_migrator import FakeSchemaMigrator

runner = CliRunner()


def _app(fake: FakeSchemaMigrator) -> CliDependencies:
    return CliDependencies(migrate_schema=lambda: MigrateSchema(fake))


def test_help_lists_commands() -> None:
    result = runner.invoke(create_app(_app(FakeSchemaMigrator([]))), ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "version" in result.output


def test_version() -> None:
    result = runner.invoke(create_app(_app(FakeSchemaMigrator([]))), ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_migrate_reports_the_change() -> None:
    result = runner.invoke(create_app(_app(FakeSchemaMigrator(["0001"]))), ["migrate"])
    assert result.exit_code == 0
    assert "migrated: <empty> -> 0001" in result.output


def test_migrate_up_to_date() -> None:
    fake = FakeSchemaMigrator(["0001"], current="0001")
    result = runner.invoke(create_app(_app(fake)), ["migrate"])
    assert "up to date: 0001" in result.output
