import json
from pathlib import Path

from typer.testing import CliRunner

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListApis, ListBuilds
from plume.application.system.migrate_schema import MigrateSchema
from plume.interfaces.cli.main import CliDependencies, create_app
from tests.fakes.schema_migrator import FakeSchemaMigrator
from tests.fakes.stack import FakeStack

runner = CliRunner()


def _app(stack: FakeStack):  # type: ignore[no-untyped-def]
    return create_app(
        CliDependencies(
            migrate_schema=lambda: MigrateSchema(FakeSchemaMigrator([])),
            build_pipeline=stack.pipeline,
            list_apis=lambda: ListApis(stack.apis),
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds),
            tag_build=stack.tag,
        )
    )


def test_load_apis_builds_tag(packages: Path) -> None:
    stack = FakeStack()
    app = _app(stack)
    result = runner.invoke(app, ["load", str(packages / "test-catalog"), "--json"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["api"] == "test-catalog-api"
    assert summary["tag"] == "latest"

    out = runner.invoke(app, ["apis"]).output
    assert "test-catalog-api\tTest Catalog API\te-commerce" in out
    out = runner.invoke(app, ["builds", "test-catalog-api"]).output
    assert summary["build"] in out
    assert "sealed" in out
    assert "latest" in out

    again = runner.invoke(app, ["load", str(packages / "test-catalog")])
    assert "reused sealed build" in again.output

    tagged = runner.invoke(app, ["tag", summary["build"], "stable"])
    assert "stable: <none> ->" in tagged.output
    diff = runner.invoke(app, ["diff", summary["build"], summary["build"]])
    assert json.loads(diff.output)["added"] == []


def test_load_errors_exit_1(tmp_path: Path) -> None:
    result = runner.invoke(_app(FakeStack()), ["load", str(tmp_path)])
    assert result.exit_code == 1
    assert "no connector/app.json" in result.output


def test_load_no_tag(packages: Path) -> None:
    stack = FakeStack()
    result = runner.invoke(_app(stack), ["load", str(packages / "second-catalog"), "--no-tag"])
    assert result.exit_code == 0
    assert "tag " not in result.output
