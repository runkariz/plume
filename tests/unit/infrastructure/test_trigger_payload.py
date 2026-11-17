"""Trigger events' payloadSchemaRef / sampleRef: the payload schema's fields and sample, or the
connector model the ref names; companion files are not triggers; unresolved refs warn once."""

import json
import shutil
from pathlib import Path

from plume.application.reader.sections import trigger_view
from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.stream_package import StreamPackageSource

source = StreamPackageSource()
SCHEMA = {
    "type": "object",
    "required": ["id"],
    "properties": {
        "id": {"type": "integer", "description": "Cart id"},
        "line_items": {"type": "array", "items": {"properties": {"sku": {"type": "string"}}}},
    },
}
SAMPLE = {"id": 7, "line_items": [{"sku": "A-1"}]}


def payload_package(packages: Path, tmp_path: Path) -> Path:
    """shopify-mini with a payload schema + sample (carts/create), a model ref by file
    (draft_orders/create), a model ref by name and a schema that only $refs a model, and two
    unresolvable refs (app/scopes_update)."""
    dst = tmp_path / "shopify-payloads"
    shutil.copytree(packages / "shopify-mini", dst)
    events = dst / "connector" / "triggers" / "events"

    def patch(name: str, **extra: str) -> None:
        path = events / name
        path.write_text(json.dumps({**json.loads(path.read_text()), **extra}))

    def event(name: str, key: str, ref: str) -> None:
        (events / name).write_text(
            json.dumps({"key": key, "title": key, "delivery": "webhook", "payloadSchemaRef": ref})
        )

    (events / "carts-create.payload.schema.json").write_text(json.dumps(SCHEMA))
    (events / "carts-create.payload.sample.json").write_text(json.dumps(SAMPLE))
    patch(
        "carts-create.json",
        payloadSchemaRef="carts-create.payload.schema.json",
        sampleRef="carts-create.payload.sample.json",
    )
    patch("draft-orders-create.json", payloadSchemaRef="../../models/customer.schema.json")
    event("customers-create.json", "customers/create", "model:address")
    (events / "orders-paid.payload.schema.json").write_text(
        json.dumps({"$ref": "../../models/lineitem.schema.json"})
    )
    event("orders-paid.json", "orders/paid", "orders-paid.payload.schema.json")
    patch("app-scopes-update.json", payloadSchemaRef="nope.json", sampleRef="../../../x.json")
    return dst


def _triggers(root: Path) -> tuple[dict[str, Document], tuple[str, ...]]:
    package = source.load(str(root))
    found = {d.source_id or "": d for d in package.documents if d.kind is DocumentKind.TRIGGER}
    return found, package.warnings


def test_payload_schema_fields_and_sample(packages: Path, tmp_path: Path) -> None:
    triggers, _ = _triggers(payload_package(packages, tmp_path))
    view = trigger_view(triggers["carts/create"])
    payload = view["payload"]
    assert payload["schema"] == SCHEMA
    assert payload["sample"] == SAMPLE
    assert payload["model"] is None
    assert payload["schema_ref"] == "carts-create.payload.schema.json"
    fields = {f["name"]: f for f in payload["fields"]}
    assert set(fields) == {"id", "line_items", "line_items[].sku"}
    assert fields["id"]["required"] is True
    assert fields["id"]["description"] == "Cart id"
    assert "## Payload fields" in triggers["carts/create"].text
    assert "`line_items[].sku` (string)" in triggers["carts/create"].text
    assert "_payload" not in view["event"]  # the event stays verbatim
    assert view["event"]["sampleRef"] == "carts-create.payload.sample.json"


def test_companion_files_are_not_triggers(packages: Path, tmp_path: Path) -> None:
    triggers, _ = _triggers(payload_package(packages, tmp_path))
    assert set(triggers) == {
        "app/scopes_update",
        "carts/create",
        "draft_orders/create",
        "customers/create",
        "orders/paid",
    }


def test_a_model_ref_links_the_model(packages: Path, tmp_path: Path) -> None:
    triggers, _ = _triggers(payload_package(packages, tmp_path))
    for key, model in (
        ("draft_orders/create", "model:customer"),
        ("customers/create", "model:address"),
        ("orders/paid", "model:lineitem"),
    ):
        payload = trigger_view(triggers[key])["payload"]
        assert payload["model"]["doc_id"] == model, key
        assert payload["schema"] is None
        assert payload["fields"] == []
        assert f"(`{model}`)" in triggers[key].text


def test_unresolved_refs_give_one_warning(packages: Path, tmp_path: Path) -> None:
    triggers, warnings = _triggers(payload_package(packages, tmp_path))
    mine = [w for w in warnings if w.startswith("triggers:")]
    assert len(mine) == 1
    assert "2 payload ref(s) not found" in mine[0]
    assert "payloadSchemaRef nope.json" in mine[0]
    assert "sampleRef ../../../x.json" in mine[0]  # outside the connector: not read
    payload = trigger_view(triggers["app/scopes_update"])["payload"]
    assert payload["schema"] is None
    assert payload["sample"] is None
    assert payload["fields"] == []


def test_events_without_refs_are_unchanged(packages: Path) -> None:
    triggers, warnings = _triggers(packages / "shopify-mini")
    assert all(trigger_view(d)["payload"] is None for d in triggers.values())
    assert not [w for w in warnings if w.startswith("triggers:")]
