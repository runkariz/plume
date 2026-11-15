"""$ref between schema files (model -> item model) and to #/$defs, bounded and cycle-safe."""

import json
from pathlib import Path

from plume.domain.knowledge.document import FieldLocation
from plume.infrastructure.sources.stream_package import _RefScope, _walk_fields


def _write(folder: Path, name: str, schema: dict[str, object]) -> Path:
    path = folder / name
    path.write_text(json.dumps(schema))
    return path


def _fields(folder: Path, name: str) -> dict[str, tuple[str | None, str | None]]:
    data = json.loads((folder / name).read_text())
    walked = _walk_fields(
        data, FieldLocation.MODEL, f"{name}#", scope=_RefScope(data, name, folder)
    )
    return {f.name: (f.description, f.pointer) for f in walked}


def test_sibling_file_and_defs_refs_are_followed(tmp_path: Path) -> None:
    _write(tmp_path, "order.schema.json", {
        "type": "object",
        "properties": {
            "line_items": {"type": "array", "items": {"$ref": "orderlineitem.schema.json"}},
            "billing": {"$ref": "#/$defs/Billing"},
        },
        "$defs": {"Billing": {"type": "object", "description": "Billing address.",
                              "properties": {"city": {"type": "string", "description": "City."}}}},
    })  # fmt: skip
    _write(tmp_path, "orderlineitem.schema.json", {
        "type": "object", "description": "One line of the order.",
        "properties": {"sku": {"type": "string", "description": "Product SKU."}},
    })  # fmt: skip
    fields = _fields(tmp_path, "order.schema.json")
    assert fields["line_items"][0] == "One line of the order."  # the item model's description
    assert fields["line_items[].sku"] == (
        "Product SKU.",
        "orderlineitem.schema.json#/properties/sku",  # the source of the citation
    )
    assert fields["billing"][0] == "Billing address."
    assert fields["billing.city"] == ("City.", "order.schema.json#/$defs/Billing/properties/city")


def test_cycles_stop_and_only_sibling_files_are_read(tmp_path: Path) -> None:
    _write(tmp_path, "node.schema.json", {
        "type": "object",
        "properties": {"name": {"type": "string"},
                       "children": {"type": "array", "items": {"$ref": "node.schema.json"}},
                       "outside": {"$ref": "../secret.schema.json"}},
    })  # fmt: skip
    fields = _fields(tmp_path, "node.schema.json")
    assert "children[].name" in fields  # expanded once
    assert "children[].children[].name" not in fields  # then the cycle stops
    assert "outside" in fields  # the field itself is kept
    assert not any(k.startswith("outside.") for k in fields)  # but nothing outside the folder
