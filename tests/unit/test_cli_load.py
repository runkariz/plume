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
    summary = json.loads(result.stdout)  # --json is stdout; progress goes to stderr
    assert summary["api"] == "test-catalog-api"
    assert "  embed ..." in result.stderr
    assert "  embed: " in result.stderr  # chunks embedded / total
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


def test_an_ad_hoc_eval_never_replaces_the_gate_eval(packages: Path, tmp_path: Path) -> None:
    """Tester-gold scoring (plume eval --gold <other>) replaced live quality cards: the card
    and gatePassed must stay the gate eval that plume load ran with the API's own gold."""
    from plume.infrastructure.sources.gold_file import JsonGoldSource  # noqa: PLC0415
    from plume.interfaces.cli.main import CliDependencies, create_app  # noqa: PLC0415

    gold_dir = packages.parent / "gold"
    stack = FakeStack(gold=JsonGoldSource([gold_dir]))
    app = create_app(
        CliDependencies(
            migrate_schema=lambda: MigrateSchema(FakeSchemaMigrator([])),
            build_pipeline=stack.pipeline, list_apis=lambda: ListApis(stack.apis),
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), tag_build=stack.tag,
            resolver=stack.resolver, gold=lambda: stack.gold, run_eval=stack.run_eval,
        )
    )  # fmt: skip
    assert runner.invoke(app, ["load", str(packages / "test-catalog"), "--json"]).exit_code == 0
    build = stack.resolver().resolve("test-catalog-api").build.build_id
    gate = stack.evals.get(build)
    assert gate is not None  # the gate eval of plume load
    other = tmp_path / "tester.json"
    question = {"id": "t1", "kind": "search", "question": "list products", "expect": ["nope"]}
    other.write_text(json.dumps({"api": "test-catalog-api", "questions": [question]}))
    adhoc = runner.invoke(app, ["eval", "test-catalog-api", "--gold", str(other), "--json"])
    assert json.loads(adhoc.stdout)["stored"] is False
    assert stack.evals.get(build) == gate  # the card still shows the gate eval
    own = runner.invoke(app, ["eval", "test-catalog-api", "--json"])
    assert json.loads(own.stdout)["stored"] is True  # the API's own gold: stored as before
