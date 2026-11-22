"""Entry point for the ``plume`` console script."""

from typing import Any

import typer

from plume.application.ports.job_events import JobEvent, JobEvents
from plume.bootstrap.container import Container
from plume.interfaces.cli.main import CliDependencies, create_app


class _Tee:
    """Job events to the container's log and to the CLI's progress."""

    def __init__(self, *sinks: JobEvents) -> None:
        self._sinks = sinks

    def emit(self, event: JobEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


def _tee(log: JobEvents, extra: JobEvents | None) -> JobEvents:
    return log if extra is None else _Tee(log, extra)


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

    def import_gold(
        package: str, out: str
    ) -> tuple[dict[str, int], list[str], dict[str, int] | None, list[str]]:
        from plume.infrastructure.sources.gold_import import import_gold as run  # noqa: PLC0415

        return run(package, out)

    def import_model_gold(text: str, group: str | None, held_out: bool) -> dict[str, Any]:
        from plume.infrastructure.models.gold_markdown import (  # noqa: PLC0415
            import_markdown,
            import_set_markdown,
            is_set_report,
        )

        if is_set_report(text):  # a set report: its relation table
            return import_set_markdown(text, group, held_out)
        return import_markdown(text, group, held_out)

    def openapi() -> str:
        from plume.bootstrap.servers import openapi_document  # noqa: PLC0415

        return openapi_document(c())

    return create_app(
        CliDependencies(
            migrate_schema=lambda: c().migrate_schema(),
            build_pipeline=lambda events: c().build_pipeline(_tee(c().events, events)),
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
            release_notes=lambda: c().release_notes(),
            remove_api=lambda: c().remove_api(),
            import_gold=import_gold,
            model_evaluation=lambda: c().model_evaluation(),
            import_model_gold=import_model_gold,
            reports=lambda: c().reported_questions,
            mapping_reports=lambda: c().mapping_reports,
        )
    )


def main() -> None:
    build_app()()
