"""Spec-derived gold questions: gold-import keeps their source and provenance, maps
``model:<name>`` items, and reports counts per source."""

import json
import shutil
from pathlib import Path

from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.gold_import import import_gold


def _with_spec_gold(packages: Path, tmp_path: Path) -> Path:
    pkg = tmp_path / "woo-mini"
    shutil.copytree(packages / "woo-mini", pkg)
    models = pkg / "connector" / "models"
    models.mkdir()
    (models / "coupon.schema.json").write_text(
        json.dumps(
            {"title": "Coupon", "type": "object", "properties": {"code": {"type": "string"}}}
        )
    )
    export = pkg / "knowledge-export"
    gold = json.loads((export / "gold-questions.json").read_text())
    gold["questions"][0]["source"] = "docs"  # explicit; the others have none (= docs)
    gold["questions"] += [
        {
            "id": "s-1",
            "source": "spec",
            "question": "Which field of a coupon holds its code?",
            "expectedItemIds": ["get-wp-json-wc-v3-coupons", "model:Coupon"],
            "expectedAnchors": [],
            "sourceUrl": "https://example.com/openapi.json",
            "specFile": "_sources/openapi.json",
            "operationId": "listCoupons",
            "quote": "Limit result set to resources with a specific code.",
            "quoteField": "parameters[code].description",
        },
        {
            "id": "s-2",
            "source": "spec",
            "question": "What does a coupon look like?",
            "expectedItemIds": ["model:coupon"],  # by file stem, any case
            "specFile": "_sources/openapi.json",
            "operationId": None,
            "quote": "Coupon",
        },
        {
            "id": "s-3",
            "source": "spec",
            "question": "Unknown model",
            "expectedItemIds": ["model:Nope"],
        },
    ]
    (export / "gold-questions.json").write_text(json.dumps(gold))
    index = json.loads((export / "index.json").read_text())
    index["goldCounts"] = {"docs": 3, "spec": 3}
    (export / "index.json").write_text(json.dumps(index))
    return pkg


def test_gold_import_keeps_source_and_spec_provenance(packages: Path, tmp_path: Path) -> None:
    out = tmp_path / "woocommerce.json"
    counts, skipped, declared, _ = import_gold(str(_with_spec_gold(packages, tmp_path)), str(out))
    assert counts == {"docs": 3, "spec": 2}
    assert skipped == ["s-3"]
    assert declared == {"docs": 3, "spec": 3}
    raw = {q["id"]: q for q in json.loads(out.read_text())["questions"]}
    s1 = raw["s-1"]
    assert s1["source"] == "spec"
    assert s1["expect"] == ["endpoint:GET~/wp-json/wc/{version}/coupons", "model:coupon"]
    assert (s1["specFile"], s1["operationId"], s1["quoteField"]) == (
        "_sources/openapi.json",
        "listCoupons",
        "parameters[code].description",
    )
    assert raw["s-2"]["expect"] == ["model:coupon"]
    assert "operationId" not in raw["s-2"]  # null is not written
    assert all(raw[q]["source"] == "docs" for q in raw if not q.startswith("s-"))
    gold, _ = JsonGoldSource().load(str(out))
    assert {q.qid: q.source for q in gold.questions}["s-2"] == "spec"


def test_plain_package_reports_docs_only(packages: Path, tmp_path: Path) -> None:
    counts, skipped, declared, _ = import_gold(str(packages / "woo-mini"), str(tmp_path / "w.json"))
    assert (counts, skipped, declared) == ({"docs": 3}, [], None)


def test_gold_file_without_source_reads_as_docs(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text(
        json.dumps({"api": "x", "questions": [{"id": "a", "question": "q", "expect": ["d"]}]})
    )
    gold, _ = JsonGoldSource().load(str(path))
    assert gold.questions[0].source == "docs"
