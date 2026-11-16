"""The ``plume`` command line. Use cases are injected; this module never touches infrastructure."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import typer

from plume import __version__
from plume.application.errors import ApplicationError
from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.export_dump import ExportDump, RestoreDump
from plume.application.knowledge.list_builds import ListApis, ListBuilds
from plume.application.knowledge.release_notes import ReleaseNotes
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.eval_repo import GoldSource
from plume.application.reader.resolve import BuildResolver
from plume.application.system.migrate_schema import MigrateSchema
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.errors import DomainError
from plume.domain.shared.ids import BuildId


@dataclass(frozen=True, slots=True)
class CliDependencies:
    """Factories, so ``plume --help`` never builds a database engine."""

    migrate_schema: Callable[[], MigrateSchema]
    build_pipeline: Callable[[], BuildPipeline] | None = None
    list_apis: Callable[[], ListApis] | None = None
    list_builds: Callable[[], ListBuilds] | None = None
    diff_builds: Callable[[], DiffBuilds] | None = None
    tag_build: Callable[[], TagBuild] | None = None
    new_job_id: Callable[[], str] = lambda: "job-cli"
    serve_api: Callable[[str | None, int | None], None] | None = None
    serve_mcp: Callable[[str | None, int | None], None] | None = None
    openapi: Callable[[], str] | None = None
    resolver: Callable[[], BuildResolver] | None = None
    run_eval: Callable[[], RunEvalGate] | None = None
    gold: Callable[[], GoldSource] | None = None
    export_dump: Callable[[], ExportDump] | None = None
    restore_dump: Callable[[], RestoreDump] | None = None
    import_gold: Callable[[str, str], tuple[int, list[str]]] | None = None
    release_notes: Callable[[], ReleaseNotes] | None = None


def _need[T](factory: Callable[[], T] | None, name: str) -> T:
    if factory is None:
        raise typer.BadParameter(f"{name} is not available in this build")
    return factory()


def create_app(deps: CliDependencies) -> typer.Typer:
    app = typer.Typer(
        name="plume",
        help="Plume: API documentation knowledge base (builds, tags, search, MCP).",
        no_args_is_help=True,
        add_completion=False,
    )

    def fail(exc: Exception) -> typer.Exit:
        typer.echo(f"error: {exc}", err=True)
        return typer.Exit(code=1)

    @app.callback()
    def main(
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log job events")] = False,
    ) -> None:
        logging.basicConfig(
            level=logging.INFO if verbose else logging.WARNING, format="%(message)s"
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

    @app.command()
    def load(
        package: Annotated[str, typer.Argument(help="Package directory (contains connector/)")],
        tag: Annotated[str | None, typer.Option(help="Tag to point at the build")] = "latest",
        no_tag: Annotated[bool, typer.Option("--no-tag", help="Build only, no tag")] = False,
        api: Annotated[str | None, typer.Option(help="Expected API id (safety check)")] = None,
        gold: Annotated[
            str | None, typer.Option(help="Gold set file (default: PLUME_GOLD_DIRS/<api>.json)")
        ] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    ) -> None:
        """Import a package: build -> chunk -> embed -> facts -> seal -> eval gate -> tag.

        Exit code 2 when the quality gate fails (the build is sealed but not tagged)."""
        pipeline = _need(deps.build_pipeline, "load")
        try:
            result = pipeline.execute(
                deps.new_job_id(),
                package,
                tag=None if no_tag else tag,
                api_id=ApiId(api) if api else None,
                gold_ref=gold,
            )
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        summary = {
            "api": result.api_id.value,
            "build": result.build_id.value,
            "reused": result.reused,
            "documents": result.documents,
            "chunks": result.chunks,
            "embedded": result.embedded,
            "from_cache": result.from_cache,
            "facts": result.facts,
            "tag": result.tag.tag if result.tag else None,
            "previous": result.tag.previous.value if result.tag and result.tag.previous else None,
            "gate": (
                {
                    "passed": result.gate.passed,
                    "message": result.gate.message,
                    "metrics": result.gate.metrics,
                    "baseline": result.gate.baseline,
                }
                if result.gate
                else None
            ),
            "notes": result.notes,
        }
        gate_failed = result.gate is not None and not result.gate.passed
        if as_json:
            typer.echo(json.dumps(summary))
            if gate_failed:
                raise typer.Exit(code=2)
            return
        if result.notes:
            c = result.notes["counts"]
            typer.echo(
                f"  release notes vs {result.notes['from']}: {c['total']} change(s); "
                f"{c['suspect']} suspect (extraction), {c['unknown']} unknown"
                + (
                    f"; NEEDS ATTENTION: {result.notes['attentionReason']}"
                    if result.notes["needsAttention"]
                    else ""
                )
            )
        state = "reused sealed build" if result.reused else "sealed"
        typer.echo(f"{result.api_id}: {result.build_id} {state}")
        typer.echo(
            f"  documents {result.documents}, chunks {result.chunks}, embedded {result.embedded}"
            f" (+{result.from_cache} cached), facts {result.facts}"
        )
        if result.gate:
            m = result.gate.metrics
            typer.echo(
                f"  eval: recall@{m['k']} {m['recall_at_k']}, MRR {m['mrr']}, "
                f"facts {m['fact_accuracy']} - {result.gate.message}"
            )
        if result.tag:
            typer.echo(f"  tag {result.tag.tag} -> {result.build_id}")
        if gate_failed:
            typer.echo("  not tagged: the quality gate failed", err=True)
            raise typer.Exit(code=2)

    @app.command()
    def apis() -> None:
        """List the APIs."""
        for info in _need(deps.list_apis, "apis").execute():
            category = info.category.key if info.category else "-"
            typer.echo(f"{info.api_id}\t{info.name}\t{category}")

    @app.command()
    def builds(api: Annotated[str, typer.Argument(help="API id")]) -> None:
        """List an API's builds (newest first) and their tags."""
        for view in _need(deps.list_builds, "builds").execute(ApiId(api)):
            b = view.build
            tags = ",".join(view.tags) or "-"
            digest = b.content_hash.short() if b.content_hash else "-"
            typer.echo(f"{b.build_id}\t{b.status}\t{len(b)} items\t{digest}\t{tags}")

    @app.command()
    def diff(
        old: Annotated[str, typer.Argument(help="Old build id")],
        new: Annotated[str, typer.Argument(help="New build id")],
    ) -> None:
        """Items added, changed and removed between two builds."""
        try:
            result = _need(deps.diff_builds, "diff").execute(BuildId(old), BuildId(new))
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        typer.echo(
            json.dumps(
                {
                    "added": list(result.added),
                    "changed": list(result.changed),
                    "removed": list(result.removed),
                    "unchanged": result.unchanged,
                },
                indent=2,
            )
        )

    @app.command("tag")
    def tag_cmd(
        build: Annotated[str, typer.Argument(help="Build id")],
        name: Annotated[str, typer.Argument(help="Tag name")] = "latest",
        force: Annotated[bool, typer.Option(help="Tag even if the quality gate failed")] = False,
    ) -> None:
        """Point a tag at a sealed build (publish or roll back)."""
        try:
            result = _need(deps.tag_build, "tag").execute(BuildId(build), name, force=force)
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        prev = result.previous.value if result.previous else "<none>"
        typer.echo(f"{result.api_id} {result.tag}: {prev} -> {result.build_id}")

    @app.command("eval")
    def eval_cmd(
        api: Annotated[str, typer.Argument(help="API id")],
        version: Annotated[str | None, typer.Option(help="Tag or build id")] = None,
        gold: Annotated[str | None, typer.Option(help="Gold set file")] = None,
        as_json: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Run the gold questions against a build and print the gate decision (exit 2 on fail)."""
        try:
            build = _need(deps.resolver, "eval").resolve(api, version).build
            source = _need(deps.gold, "eval")
            ref = gold or source.for_api(api)
            if ref is None:
                raise typer.BadParameter(f"no gold set for {api}; pass --gold")
            gold_set, gold_hash = source.load(ref)
            run = _need(deps.run_eval, "eval").execute(build.build_id, gold_set, gold_hash)
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        out = {
            "api": api,
            "build": build.build_id.value,
            "passed": run.decision.passed,
            "message": run.decision.message,
            "metrics": run.record.metrics.as_dict(),
            "baseline": run.baseline.build_id.value if run.baseline else None,
            "details": list(run.record.details),
        }
        typer.echo(json.dumps(out, indent=None if as_json else 2))
        if not run.decision.passed:
            raise typer.Exit(code=2)

    @app.command("gold-import")
    def gold_import(
        package: Annotated[str, typer.Argument(help="Package with knowledge-export/")],
        out: Annotated[str, typer.Option(help="Gold set file to write (<api>.json)")],
    ) -> None:
        """Convert the package's knowledge-export/gold-questions.json into a Plume gold set."""
        if deps.import_gold is None:
            raise typer.BadParameter("gold-import is not available in this build")
        try:
            count, skipped = deps.import_gold(package, out)
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        typer.echo(f"wrote {out}: {count} question(s); skipped {len(skipped)}")

    @app.command("export")
    def export_cmd(
        api: Annotated[str, typer.Argument(help="API id")],
        version: Annotated[str | None, typer.Option(help="Tag or build id")] = None,
        out: Annotated[str | None, typer.Option(help="Output file")] = None,
    ) -> None:
        """Write a sealed build as a dump (gzip JSON lines, verified)."""
        try:
            build = _need(deps.resolver, "export").resolve(api, version).build
            ref = _need(deps.export_dump, "export").execute(build.build_id, out)
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        typer.echo(ref)

    @app.command("notes")
    def notes_cmd(
        api: Annotated[str, typer.Argument(help="API id")],
        build: Annotated[
            str | None, typer.Option(help="Build id (default: the newest notes)")
        ] = None,
        as_json: Annotated[
            bool, typer.Option("--json", help="Summary as JSON (for manifests)")
        ] = False,
        issues: Annotated[bool, typer.Option(help="Print the copy-issues text for stream")] = False,
        recompute: Annotated[
            str | None, typer.Option(help="Recompute BUILD's notes against this base build")
        ] = None,
    ) -> None:
        """Release notes of a build: what changed against its predecessor (maintainer view)."""
        service = _need(deps.release_notes, "notes")
        try:
            if recompute is not None:
                if build is None:
                    raise typer.BadParameter("--recompute needs --build")
                service.compute(BuildId(recompute), BuildId(build))
            target = build or next((n["to"] for n in service.summaries(api)), None)
            if target is None:
                typer.echo(f"{api}: no release notes yet")
                return
            if issues:
                typer.echo(service.issues(api, target), nl=False)
                return
            n = service.get(api, target)
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        summary = {
            k: n[k]
            for k in (
                "api",
                "from",
                "to",
                "toDocsAsOf",
                "computedAt",
                "review",
                "counts",
                "needsAttention",
                "attentionReason",
                "extractorChanged",
                "gold",
            )
        }
        if as_json:
            typer.echo(json.dumps(summary))
            return
        c = n["counts"]
        typer.echo(f"{api}: {n['from']} -> {n['to']} ({n['review']})")
        typer.echo(
            f"  {c['confirmed']} confirmed, {c['likely']} likely, {c['suspect']} suspect, "
            f"{c['unknown']} unknown, {c['renamed']} renamed; {c['breaking']} visible breaking"
        )
        if n["needsAttention"]:
            typer.echo(f"  NEEDS ATTENTION: {n['attentionReason']}")
        for g in n["report"]:
            typer.echo(f"  {g['rule']}: {g['count']} ({g['title']})")

    @app.command("restore")
    def restore_cmd(
        dump: Annotated[str, typer.Argument(help="Dump file")],
        tag: Annotated[list[str] | None, typer.Option(help="Tags to set (repeatable)")] = None,
    ) -> None:
        """Restore a dump into the database in one transaction (verified first)."""
        try:
            r = _need(deps.restore_dump, "restore").execute(dump, tag or [])
        except (ApplicationError, DomainError) as exc:
            raise fail(exc) from exc
        state = "restored" if r.restored else "already present"
        typer.echo(
            f"{r.api}: {r.build} {state} ({r.documents} documents, {r.chunks} chunks, "
            f"{r.facts} facts){' tags ' + ','.join(r.tags) if r.tags else ''}"
        )

    @app.command()
    def serve(
        host: Annotated[str | None, typer.Option(help="Bind address")] = None,
        port: Annotated[int | None, typer.Option(help="Port (default 18480)")] = None,
    ) -> None:
        """Run the HTTP API."""
        if deps.serve_api is None:
            raise typer.BadParameter("serve is not available in this build")
        deps.serve_api(host, port)

    @app.command()
    def mcp(
        host: Annotated[str | None, typer.Option(help="Bind address")] = None,
        port: Annotated[int | None, typer.Option(help="Port (default 18481)")] = None,
    ) -> None:
        """Run the reader MCP server (streamable HTTP at /mcp)."""
        if deps.serve_mcp is None:
            raise typer.BadParameter("mcp is not available in this build")
        deps.serve_mcp(host, port)

    @app.command()
    def openapi(
        out: Annotated[
            str | None, typer.Option(help="Write to this file instead of stdout")
        ] = None,
    ) -> None:
        """Print the OpenAPI document of the HTTP API."""
        doc = _need(deps.openapi, "openapi")
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(doc)
            typer.echo(f"wrote {out}")
        else:
            typer.echo(doc, nl=False)

    return app
