"""Schemas whose references fan out (an entity graph, Shopware-like) list at most
MAX_WALK_FIELDS fields: the deepest nesting level that fits, with a note. Small schemas are
listed in full, as before."""

import json
import shutil
from pathlib import Path

import pytest

from plume.application.ports.package_source import SourcePackage
from plume.domain.knowledge.document import FIELDS_BOUNDED_KEY, DocumentKind
from plume.infrastructure.sources.stream_package import (
    MAX_FIELD_DEPTH,
    MAX_WALK_FIELDS,
    StreamPackageSource,
)
from tests.conftest import PACKAGES
from tests.fakes.stack import FakeStack

ENTITIES = [f"entity{i}" for i in range(12)]


@pytest.fixture(scope="module")
def graph(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _graph_package(PACKAGES, tmp_path_factory.mktemp("bounded"))


@pytest.fixture(scope="module")
def loaded(graph: Path) -> SourcePackage:
    return StreamPackageSource().load(str(graph))


@pytest.fixture(scope="module")
def stack(graph: Path) -> FakeStack:
    s = FakeStack()
    s.load(str(graph))
    return s


def _graph_package(packages: Path, tmp_path: Path) -> Path:
    """shopify-mini plus 12 models that each reference all the others (with own fields)."""
    dst = tmp_path / "graph"
    shutil.copytree(packages / "shopify-mini", dst)
    models = dst / "connector" / "models"
    for name in ENTITIES:
        props: dict[str, object] = {f"field{k}": {"type": "string"} for k in range(5)}
        props.update({f"to_{o}": {"$ref": f"{o}.schema.json"} for o in ENTITIES if o != name})
        schema = {"title": name.capitalize(), "type": "object", "properties": props}
        (models / f"{name}.schema.json").write_text(json.dumps(schema))
    return dst


def test_a_fanned_out_model_is_bounded_with_a_note(loaded: SourcePackage) -> None:
    package = loaded
    model = next(d for d in package.documents if d.doc_id == "model:entity0")
    assert 0 < len(model.fields) <= MAX_WALK_FIELDS
    names = {f.name for f in model.fields}
    assert {"field0", "to_entity1", "to_entity1.field0"} <= names  # top and first level kept
    depth = max(f.name.count(".") for f in model.fields)
    assert depth < MAX_FIELD_DEPTH
    assert f"more than {MAX_WALK_FIELDS} fields" in model.text
    assert f"up to nesting level {depth + 1}" in model.text


def test_small_models_are_listed_in_full(packages: Path, loaded: SourcePackage) -> None:
    package = loaded
    plain = StreamPackageSource().load(str(packages / "shopify-mini"))
    before = {d.doc_id: d for d in plain.documents if d.kind is DocumentKind.MODEL}
    after = {d.doc_id: d for d in package.documents if d.doc_id in before}
    assert all(after[k].fields == before[k].fields for k in before)
    assert all(after[k].text == before[k].text for k in before)
    assert all("nesting level" not in d.text for d in before.values())


def test_a_bounded_model_records_its_level(loaded: SourcePackage) -> None:
    package = loaded
    model = next(d for d in package.documents if d.doc_id == "model:entity0")
    level = (model.raw or {})[FIELDS_BOUNDED_KEY]
    assert level == max(f.name.count(".") for f in model.fields) + 1
    assert model.complete is True  # the source is complete; only Plume's list is bounded
    small = next(d for d in package.documents if d.doc_id == "model:address")
    assert FIELDS_BOUNDED_KEY not in (small.raw or {})


def test_find_fact_says_not_listed_for_a_truncated_schema(
    stack: FakeStack, loaded: SourcePackage
) -> None:
    deep = ".".join(f"to_entity{i}" for i in range(1, MAX_FIELD_DEPTH)) + ".field0"
    result = stack.find_fact().execute("shopify", deep, owner="model:entity0")
    assert result.found is False
    assert result.complete is False  # absence is not proven
    model = next(d for d in loaded.documents if d.doc_id == "model:entity0")
    level = (model.raw or {})[FIELDS_BOUNDED_KEY]
    assert result.reasons == (
        f"not listed: model:entity0 schema truncated at nesting level {level}",
    )
    assert "absence is NOT proven" in result.wording
    listed = stack.find_fact().execute("shopify", "to_entity1.field0", owner="model:entity0")
    assert listed.found is True


def test_find_fact_on_a_complete_schema_is_unchanged(stack: FakeStack) -> None:
    result = stack.find_fact().execute("shopify", "no_such_field", owner="model:address")
    assert result.found is False
    assert result.complete is True
    assert not any(r.startswith("not listed") for r in result.reasons)
