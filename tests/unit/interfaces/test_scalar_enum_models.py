"""A model whose root is a scalar enum (meta-ig TriggerType: {type: string, enum: [...],
x-enum-descriptions}) documents its values: they are in its text (searchable, read by
get_document) and in a "values" list next to its fields."""

import json
import shutil
from pathlib import Path

from plume.domain.knowledge.enum_values import enum_values
from plume.interfaces import payloads
from tests.fakes.stack import FakeStack

TRIGGER = {
    "title": "TriggerType",
    "description": "Triggers specifying when a rule fires.",
    "type": "string",
    "enum": ["always", "percentage_change", "absolute_max"],
    "x-enum-descriptions": {"always": "Fires always", "absolute_max": "Fires above a ceiling"},
    "x-complete": True,
}


def _stack(packages: Path, tmp_path: Path) -> FakeStack:
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    models = dst / "connector" / "models"
    (models / "triggertype.schema.json").write_text(json.dumps(TRIGGER))
    stack = FakeStack()
    stack.load(str(dst))
    return stack


def test_the_values_are_in_the_models_text_and_payload(packages: Path, tmp_path: Path) -> None:
    doc = _stack(packages, tmp_path).get_document().execute("shopify", "model:triggertype")
    assert doc.document.text.endswith(
        "## Values\n"
        "- `always`: Fires always\n"
        "- `percentage_change`\n"
        "- `absolute_max`: Fires above a ceiling"
    )
    assert payloads.document_payload(doc)["values"] == [
        {"value": "always", "description": "Fires always"},
        {"value": "percentage_change", "description": None},
        {"value": "absolute_max", "description": "Fires above a ceiling"},
    ]


def test_an_object_model_has_no_values(packages: Path, tmp_path: Path) -> None:
    stack = _stack(packages, tmp_path)
    model = stack.get_document().execute("shopify", "model:customer")
    assert model.document.fields
    assert "## Values" not in model.document.text
    assert payloads.document_payload(model)["values"] == []


def test_descriptions_may_be_a_list_in_enum_order() -> None:
    schema = {"enum": ["a", "b", 3], "x-enum-descriptions": ["first", " "]}
    assert enum_values(schema) == [("a", "first"), ("b", None), ("3", None)]
    assert enum_values({"type": "object", "properties": {"x": {}}, "enum": ["a"]}) == []
    assert enum_values({"type": "string"}) == []
