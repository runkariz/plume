"""The ``plume`` command line. Use cases are injected; this module never touches infrastructure."""

from collections.abc import Callable
from dataclasses import dataclass

import typer

from plume import __version__
from plume.application.system.migrate_schema import MigrateSchema


@dataclass(frozen=True, slots=True)
class CliDependencies:
    """Factories, so ``plume --help`` never builds a database engine."""

    migrate_schema: Callable[[], MigrateSchema]


def create_app(deps: CliDependencies) -> typer.Typer:
    app = typer.Typer(
        name="plume",
        help="Plume: API documentation knowledge base (builds, tags, search, MCP).",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command()
    def version() -> None:
        """Print the Plume version."""
        typer.echo(__version__)

    @app.command()
    def migrate() -> None:
        """Bring the database schema to the latest revision."""
        result = deps.migrate_schema().execute()
        if result.changed:
            typer.echo(f"migrated: {result.before or '<empty>'} -> {result.after}")
        else:
            typer.echo(f"up to date: {result.after}")

    return app
