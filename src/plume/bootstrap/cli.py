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

    def serve_api(host: str | None, port: int | None) -> None:
        from plume.bootstrap.servers import serve_api as run  # noqa: PLC0415 - server deps lazily

        run(c(), host, port)

    def serve_mcp(host: str | None, port: int | None) -> None:
        from plume.bootstrap.servers import serve_mcp as run  # noqa: PLC0415

        run(c(), host, port)

    def import_gold(package: str, out: str) -> tuple[int, list[str]]:
        from plume.infrastructure.sources.gold_import import import_gold as run  # noqa: PLC0415

        return run(package, out)

    def openapi() -> str:
        from plume.bootstrap.servers import openapi_document  # noqa: PLC0415

        return openapi_document(c())

    return create_app(
        CliDependencies(
            migrate_schema=lambda: c().migrate_schema(),
            build_pipeline=lambda: c().build_pipeline(),
            list_apis=lambda: c().list_apis(),
            list_builds=lambda: c().list_builds(),
            diff_builds=lambda: c().diff_builds(),
            tag_build=lambda: c().tag_build(),
            new_job_id=Container.new_job_id,
            serve_api=serve_api,
            serve_mcp=serve_mcp,
            openapi=openapi,
            resolver=lambda: c().resolver(),
            run_eval=lambda: c().run_eval(),
            gold=lambda: c().gold,
            export_dump=lambda: c().export_dump(),
            restore_dump=lambda: c().restore_dump(),
            import_gold=import_gold,
        )
    )


def main() -> None:
    build_app()()
