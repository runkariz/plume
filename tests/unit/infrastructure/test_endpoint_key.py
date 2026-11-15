import json
from pathlib import Path

from plume.infrastructure.sources.gold_file import convert_stream_gold
from plume.infrastructure.sources.stream_package import endpoint_key

VERSIONS = ("2026-10",)


def test_declared_version_suffix_is_stripped() -> None:
    assert endpoint_key("get-admin-api-latest-orders-json-2026-10", VERSIONS) == (
        "get-admin-api-latest-orders-json"
    )
    assert endpoint_key("get-admin-api-latest-orders-json", VERSIONS) == (
        "get-admin-api-latest-orders-json"
    )


def test_only_declared_versions_are_stripped() -> None:
    assert endpoint_key("get-orders-2025-01", VERSIONS) == "get-orders-2025-01"
    assert endpoint_key("get-orders-2026-10", ()) == "get-orders-2026-10"


def test_gold_maps_ids_across_versions(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    q = {"id": "q1", "question": "list orders", "expectedItemIds": ["get-orders-json"]}
    gold.write_text(json.dumps({"questions": [q]}))
    ids = {"get-orders-json": "endpoint:GET~/orders.json"}
    data, skipped = convert_stream_gold(gold, "shop", ids, lambda i: endpoint_key(i, VERSIONS))
    assert not skipped
    assert "endpoint:GET~/orders.json" in json.dumps(data)
