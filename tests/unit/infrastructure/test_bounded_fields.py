"""Schemas whose references fan out (an entity graph, Shopware-like) list at most
MAX_WALK_FIELDS fields: the deepest nesting level that fits, with a note. Small schemas are
listed in full, as before."""

import json
import shutil
from pathlib import Path

from plume.domain.knowledge.document import DocumentKind
from plume.infrastructure.sources.stream_package import (
    MAX_FIELD_DEPTH,
    MAX_WALK_FIELDS,
    StreamPackageSource,
)

ENTITIES = [f"entity{i}" for i in range(12)]


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


def test_a_fanned_out_model_is_bounded_with_a_note(packages: Path, tmp_path: Path) -> None:
    package = StreamPackageSource().load(str(_graph_package(packages, tmp_path)))
    model = next(d for d in package.documents if d.doc_id == "model:entity0")
    assert 0 < len(model.fields) <= MAX_WALK_FIELDS
    names = {f.name for f in model.fields}
    assert {"field0", "to_entity1", "to_entity1.field0"} <= names  # top and first level kept
    depth = max(f.name.count(".") for f in model.fields)
    assert depth < MAX_FIELD_DEPTH
    assert f"more than {MAX_WALK_FIELDS} fields" in model.text
    assert f"up to nesting level {depth + 1}" in model.text


def test_small_models_are_listed_in_full(packages: Path, tmp_path: Path) -> None:
    package = StreamPackageSource().load(str(_graph_package(packages, tmp_path)))
    plain = StreamPackageSource().load(str(packages / "shopify-mini"))
    before = {d.doc_id: d for d in plain.documents if d.kind is DocumentKind.MODEL}
    after = {d.doc_id: d for d in package.documents if d.doc_id in before}
    assert all(after[k].fields == before[k].fields for k in before)
    assert all(after[k].text == before[k].text for k in before)
    assert all("nesting level" not in d.text for d in before.values())
