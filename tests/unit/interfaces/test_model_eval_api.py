"""Model gold over HTTP: POST /v1/models/{id}/eval (maintainer) and `eval` on a succeeded
generation job; and the CLI's model-eval / model-gold-import."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.models.model_eval import ModelEvaluation
from plume.application.system.migrate_schema import MigrateSchema
from plume.infrastructure.models.gold_files import JsonModelGold
from plume.infrastructure.models.gold_markdown import import_markdown
from plume.interfaces.cli.main import CliDependencies
from plume.interfaces.cli.main import create_app as create_cli
from plume.interfaces.http.app import HttpDependencies, create_app
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.schema_migrator import FakeSchemaMigrator
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
A, B = APIS
TOKEN = "pl_eval_test"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
GOLD = {
    "schema": "plume.model-gold.v1",
    "concept": "Order",
    "apis": APIS,
    "fields": [
        {"name": "id", "apis": {A: {"paths": ["id"]}, B: {"paths": ["id"]}}},
        {"name": "total", "apis": {A: {"paths": ["orders[].total"]}, B: {"paths": ["total"]}}},
        {"name": "currency", "apis": {A: {"paths": ["currency"]}, B: {"paths": ["number"]}}},
    ],
}


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


@pytest.fixture
def evaluation(stack: FakeStack, tmp_path: Path) -> ModelEvaluation:
    folder = tmp_path / "gold"
    folder.mkdir()
    (folder / "order-1.json").write_text(json.dumps(GOLD))
    return ModelEvaluation(
        stack.models_repo, stack.sets_repo, stack.models().oracle_for, JsonModelGold((folder,))
    )


@pytest.fixture
def client(stack: FakeStack, evaluation: ModelEvaluation) -> TestClient:
    return TestClient(
        create_app(
            HttpDependencies(
                overviews=stack.overviews,
                browse=stack.browse,
                search=stack.search,
                get_document=stack.get_document,
                find_fact=stack.find_fact,
                check_call=stack.check_call,
                list_builds=lambda: ListBuilds(stack.builds, stack.tags),
                diff_builds=lambda: DiffBuilds(stack.builds),
                resolver=stack.resolver,
                rate_limit_per_minute=0,
                suggest=stack.suggest,
                models=stack.models,
                maintainer_tokens=(TOKEN,),
                generate_models=stack.generate,
                model_evaluation=lambda: evaluation,
            )
        )
    )


def _good() -> dict[str, Any]:
    return json.loads((DRAFTS / "catalog-order-good.json").read_text())  # type: ignore[no-any-return]


def test_generation_job_carries_its_eval_and_the_eval_route(
    stack: FakeStack, client: TestClient
) -> None:
    stack.writer.replies = [_good()]
    job = client.post(
        "/v1/models/generate", headers=AUTH, json={"apis": APIS, "concept": "Order"}
    ).json()
    done = client.get(f"/v1/models/jobs/{job['jobId']}", headers=AUTH).json()
    assert done["status"] == "succeeded"
    [result] = done["eval"]["results"]
    assert result["counts"] == {"correct": 5, "wrong": 1}  # B's currency: gold says "number"
    assert result["recall"] == round(5 / 6, 4)
    wrong = next(c for c in result["cells"] if c["result"] == "wrong")
    assert (wrong["field"], wrong["api"], wrong["produced"]) == ("currency", B, ["currency"])
    assert done["eval"]["heldOut"]["models"] == 0
    mid = done["snapshotId"]
    direct = client.post(f"/v1/models/{mid}/eval", headers=AUTH).json()
    assert direct["results"] == done["eval"]["results"]
    by_name = client.post(f"/v1/models/{mid}/eval", headers=AUTH, params={"gold": "order-1.json"})
    assert by_name.status_code == 200
    assert client.post(f"/v1/models/{mid}/eval").status_code == 401
    bad = client.post(f"/v1/models/{mid}/eval", headers=AUTH, params={"gold": "../x.json"})
    assert bad.status_code == 422  # a file name in the gold dirs, never a path
    assert client.post("/v1/models/m-nope/eval", headers=AUTH).status_code == 404


def test_cli_model_eval_and_gold_import(
    stack: FakeStack, evaluation: ModelEvaluation, tmp_path: Path
) -> None:
    session = stack.models().start(APIS, "Order")
    sid = stack.models().submit(session.session_id, _good(), maintainer=True).snapshot.snapshot_id
    cli = create_cli(
        CliDependencies(
            migrate_schema=lambda: MigrateSchema(FakeSchemaMigrator([])),
            model_evaluation=lambda: evaluation,
            import_model_gold=import_markdown,
        )
    )
    runner = CliRunner()
    out = runner.invoke(cli, ["model-eval", sid])
    assert out.exit_code == 0, out.output
    assert "precision 0.8333, recall 0.8333, invented 0" in out.output
    assert "wrong: currency on second-catalog-api: expected number, produced currency" in out.output
    as_json = json.loads(runner.invoke(cli, ["model-eval", sid, "--json"]).stdout)
    assert as_json["tuning"]["recall"] == round(5 / 6, 4)
    report = tmp_path / "order.md"
    report.write_text(
        "# Order across test-catalog-api, second-catalog-api, tested 2026-11-20\n"
        "## Expected mapping (gold)\n"
        "| canonical field | test-catalog-api | second-catalog-api | conversion |\n"
        "|---|---|---|---|\n"
        "| id | `id` | `id` | |\n| status | not available | `status` | enum |\n"
    )
    gold_file = tmp_path / "order-gold.json"
    imported = runner.invoke(
        cli, ["model-gold-import", str(report), "--out", str(gold_file), "--held-out"]
    )
    assert imported.exit_code == 0, imported.output
    assert (
        "Order on test-catalog-api, second-catalog-api; 3 expected mapping(s), 1 not available"
        in imported.output
    )
    assert json.loads(gold_file.read_text())["heldOut"] is True
    held = runner.invoke(cli, ["model-eval", sid, "--gold", str(gold_file), "--json"])
    assert json.loads(held.stdout)["heldOut"]["models"] == 1
