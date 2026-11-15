"""Entry point for the ``plume`` console script."""

import typer

from plume.bootstrap.container import Container
from plume.interfaces.cli.main import CliDependencies, create_app


def build_app(container: Container | None = None) -> typer.Typer:
    holder: list[Container] = [container] if container is not None else []

    def get_container() -> Container:
        if not holder:
            holder.append(Container())
        return holder[0]

    return create_app(CliDependencies(migrate_schema=lambda: get_container().migrate_schema()))


def main() -> None:
    build_app()()
