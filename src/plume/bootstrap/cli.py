"""Entry point for the ``plume`` console script."""

import typer

from plume.bootstrap.container import Container
from plume.interfaces.cli.main import CliDependencies, create_app


def build_app(container: Container | None = None) -> typer.Typer:
    holder: list[Container] = [container] if container is not None else []

    def c() -> Container:
        if not holder:
            holder.append(Container())
        return holder[0]

    return create_app(
        CliDependencies(
            migrate_schema=lambda: c().migrate_schema(),
            build_pipeline=lambda: c().build_pipeline(),
            list_apis=lambda: c().list_apis(),
            list_builds=lambda: c().list_builds(),
            diff_builds=lambda: c().diff_builds(),
            tag_build=lambda: c().tag_build(),
            new_job_id=Container.new_job_id,
        )
    )


def main() -> None:
    build_app()()
