import json
import shutil
from pathlib import Path

import pytest

from plume.application.errors import (
    EmbeddingError,
    IncompleteBuildError,
    NotFoundError,
    SourcePackageError,
)
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListApis, ListBuilds
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.fact import FactKind
from plume.domain.knowledge.tag import TagName
from plume.domain.shared.errors import TagTargetError
from plume.domain.shared.ids import BuildId
from tests.fakes.knowledge import DeterministicEmbedder
from tests.fakes.stack import FakeStack

CATALOG = ApiId("test-catalog-api")


def _edited_copy(packages: Path, tmp_path: Path) -> Path:
    """test-catalog with one model changed, one removed and one guide added."""
    copy = tmp_path / "catalog-v2"
    shutil.copytree(packages / "test-catalog", copy)
    order = copy / "connector" / "models" / "order.schema.json"
    data = json.loads(order.read_text())
    data["properties"]["status"] = {"type": "string", "description": "Order status."}
    order.write_text(json.dumps(data))
    (copy / "connector" / "models" / "error.schema.json").unlink()
    export = copy / "knowledge-export"
    export.mkdir()
    (export / "faq.md").write_text("# FAQ\n\nOrders are immutable after shipping.\n")
    return copy


def test_full_pipeline_seals_and_tags(packages: Path) -> None:
    stack = FakeStack()
    result = stack.pipeline().execute("job-1", str(packages / "test-catalog"))
    build = stack.builds.get(result.build_id)
    assert build is not None
    assert build.is_sealed
    assert result.documents == 9  # + the environments guide
    assert result.chunks == len(build) > 0
    assert result.embedded == result.chunks
    assert result.facts > 0
    assert result.tag is not None
    assert result.tag.previous is None
    tag = stack.tags.get(CATALOG, TagName("latest"))
    assert tag is not None
    assert tag.build_id == result.build_id
    assert stack.vectors.missing(result.build_id) == []
    assert stack.events.steps() == [
        ("import", "started"), ("import", "done"),
        ("chunk", "started"), ("chunk", "done"),
        ("embed", "started"), ("embed", "done"),
        ("facts", "started"), ("facts", "done"),
        ("seal", "started"), ("seal", "done"),
        ("evaluate", "skipped"),
        ("notes", "started"), ("notes", "skipped"),  # the first build has no predecessor
        ("tag", "started"), ("tag", "done"),
    ]  # fmt: skip
    progress = [e for e in stack.events.events if e.status.value == "progress"]
    assert progress
    assert progress[-1].data["done"] == result.embedded


def test_same_input_same_build_and_rerun_is_a_noop(packages: Path, tmp_path: Path) -> None:
    stack = FakeStack()
    first = stack.pipeline().execute("job-1", str(packages / "test-catalog"))
    copy = tmp_path / "same"
    shutil.copytree(packages / "test-catalog", copy)
    calls_before = len(stack.embedder.calls)
    again = stack.pipeline().execute("job-2", str(copy))
    assert again.build_id == first.build_id
    assert again.reused
    assert len(stack.embedder.calls) == calls_before
    assert ("chunk", "skipped") in stack.events.steps()

    other = FakeStack()
    assert other.pipeline().execute("j", str(packages / "test-catalog")).build_id == first.build_id


def test_second_build_reuses_cache_and_diff_names_changes(packages: Path, tmp_path: Path) -> None:
    stack = FakeStack()
    v1 = stack.pipeline().execute("job-1", str(packages / "test-catalog"))
    v2 = stack.pipeline().execute("job-2", str(_edited_copy(packages, tmp_path)))
    assert v2.build_id != v1.build_id
    assert v2.from_cache > 0
    assert v2.embedded < v2.chunks
    assert v2.tag is not None
    assert v2.tag.previous == v1.build_id

    diff = DiffBuilds(stack.builds).execute(v1.build_id, v2.build_id)
    assert diff.added == ("guide:export-faq#0",)
    assert diff.changed == ("model:order#0",)
    assert diff.removed == ("model:error#0",)
    assert diff.unchanged == v1.chunks - 2

    views = ListBuilds(stack.builds, stack.tags).execute(CATALOG)
    assert [v.build.build_id for v in views] == [v2.build_id, v1.build_id]
    assert views[0].tags == ("latest",)
    assert views[1].tags == ()
    assert [a.api_id for a in ListApis(stack.apis).execute()] == [CATALOG]


def test_rollback_moves_the_tag_back(packages: Path, tmp_path: Path) -> None:
    stack = FakeStack()
    v1 = stack.pipeline().execute("job-1", str(packages / "test-catalog"))
    v2 = stack.pipeline().execute("job-2", str(_edited_copy(packages, tmp_path)))
    back = stack.tag().execute(v1.build_id, "latest")
    assert back.previous == v2.build_id
    assert stack.tags.get(CATALOG, TagName("latest")).build_id == v1.build_id  # type: ignore[union-attr]


def test_facts_include_endpoints_fields_and_incomplete_models(packages: Path) -> None:
    stack = FakeStack()
    result = stack.pipeline().execute("job", str(packages / "shopify-mini"))
    facts = stack.facts.list_facts(result.build_id)
    kinds = {f.kind for f in facts}
    assert kinds == {FactKind.ENDPOINT, FactKind.FIELD, FactKind.SCOPE}
    assert any(
        f.name == "read_assigned_fulfillment_orders" and f.kind is FactKind.SCOPE for f in facts
    )
    customer = [f for f in facts if f.owner_id == "model:customer"]
    assert customer
    assert all(not f.complete for f in customer)


def test_draft_cannot_be_tagged_and_unknown_build(packages: Path) -> None:
    stack = FakeStack()
    imported = stack.import_package().execute(str(packages / "test-catalog"))
    with pytest.raises(TagTargetError):
        stack.tag().execute(imported.build_id, "latest")
    with pytest.raises(NotFoundError):
        stack.tag().execute(BuildId.new(), "latest")


def test_seal_requires_every_chunk_embedded(packages: Path) -> None:
    stack = FakeStack()
    imported = stack.import_package().execute(str(packages / "test-catalog"))
    stack.chunk().execute(imported.build_id)
    with pytest.raises(IncompleteBuildError):
        stack.seal().execute(imported.build_id)


def test_failed_embed_can_be_resumed(packages: Path) -> None:
    stack = FakeStack(batch_size=1)
    stack.embedder.fail_on = "List products"
    with pytest.raises(EmbeddingError):
        stack.pipeline().execute("job-1", str(packages / "test-catalog"))
    assert ("embed", "failed") in stack.events.steps()
    done_before = sum(stack.embedder.calls) - 1  # the failing batch returned nothing
    stack.embedder.fail_on = None
    result = stack.pipeline().execute("job-2", str(packages / "test-catalog"))
    assert done_before > 0
    # Vectors stored before the failure stay on their chunks; only the rest is embedded.
    assert result.embedded == result.chunks - done_before
    assert stack.builds.get(result.build_id).is_sealed  # type: ignore[union-attr]


def test_embedder_mismatch_is_refused(packages: Path) -> None:
    stack = FakeStack()
    imported = stack.import_package().execute(str(packages / "test-catalog"))
    stack.chunk().execute(imported.build_id)
    stack.embedder = DeterministicEmbedder(model="other-model")
    with pytest.raises(EmbeddingError, match="expects"):
        stack.embed().execute(imported.build_id)


def test_api_guard(packages: Path) -> None:
    with pytest.raises(SourcePackageError, match="not shopify"):
        FakeStack().import_package().execute(str(packages / "test-catalog"), ApiId("shopify"))


def test_two_apis_side_by_side(packages: Path) -> None:
    stack = FakeStack()
    a = stack.pipeline().execute("a", str(packages / "test-catalog"))
    b = stack.pipeline().execute("b", str(packages / "second-catalog"))
    assert a.api_id != b.api_id
    with pytest.raises(Exception, match="different APIs"):
        DiffBuilds(stack.builds).execute(a.build_id, b.build_id)
